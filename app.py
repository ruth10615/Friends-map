import os
from typing import Any

import folium
import streamlit as st
from folium.plugins import MarkerCluster
from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim
from streamlit_folium import st_folium
from supabase import Client, create_client


# ---------------------------------------------------------
# Page configuration
# ---------------------------------------------------------
st.set_page_config(
    page_title="Friends Map",
    page_icon="🌍",
    layout="wide",
)


# ---------------------------------------------------------
# Supabase connection
# ---------------------------------------------------------
@st.cache_resource
def get_supabase_client() -> Client:
    """Create and cache the Supabase client."""
    try:
        supabase_url = st.secrets["SUPABASE_URL"]
        supabase_key = st.secrets["SUPABASE_KEY"]
    except KeyError as exc:
        raise RuntimeError(
            "找不到 Supabase Secrets。請設定 SUPABASE_URL 和 SUPABASE_KEY。"
        ) from exc

    return create_client(supabase_url, supabase_key)


supabase = get_supabase_client()


# ---------------------------------------------------------
# Geocoder
# ---------------------------------------------------------
@st.cache_resource
def get_geocoder() -> Nominatim:
    return Nominatim(user_agent="friends-map-streamlit-app")


geocoder = get_geocoder()


@st.cache_data(show_spinner=False, ttl=86400)
def geocode_city(city: str, country: str) -> tuple[float, float] | None:
    """Convert a city and country into latitude and longitude."""
    query = ", ".join(part.strip() for part in [city, country] if part.strip())

    if not query:
        return None

    try:
        location = geocoder.geocode(query, timeout=10)
    except (GeocoderTimedOut, GeocoderServiceError):
        return None

    if location is None:
        return None

    return float(location.latitude), float(location.longitude)


# ---------------------------------------------------------
# Supabase CRUD
# ---------------------------------------------------------
def get_friends() -> list[dict[str, Any]]:
    response = (
        supabase.table("friends")
        .select("*")
        .order("name")
        .execute()
    )
    return response.data or []


def add_friend(
    name: str,
    city: str,
    country: str,
    latitude: float,
    longitude: float,
    notes: str,
) -> dict[str, Any]:
    payload = {
        "name": name.strip(),
        "city": city.strip(),
        "country": country.strip(),
        "latitude": latitude,
        "longitude": longitude,
        "notes": notes.strip(),
    }

    response = supabase.table("friends").insert(payload).execute()

    if not response.data:
        raise RuntimeError("Supabase 沒有回傳新增資料。")

    return response.data[0]


def update_friend(
    friend_id: int,
    name: str,
    city: str,
    country: str,
    latitude: float,
    longitude: float,
    notes: str,
) -> dict[str, Any]:
    payload = {
        "name": name.strip(),
        "city": city.strip(),
        "country": country.strip(),
        "latitude": latitude,
        "longitude": longitude,
        "notes": notes.strip(),
    }

    response = (
        supabase.table("friends")
        .update(payload)
        .eq("id", friend_id)
        .execute()
    )

    if not response.data:
        raise RuntimeError("Supabase 沒有回傳更新資料。")

    return response.data[0]


def delete_friend(friend_id: int) -> None:
    supabase.table("friends").delete().eq("id", friend_id).execute()


# ---------------------------------------------------------
# Map
# ---------------------------------------------------------
def create_map(friends: list[dict[str, Any]]) -> folium.Map:
    if friends:
        avg_lat = sum(float(friend["latitude"]) for friend in friends) / len(friends)
        avg_lon = sum(float(friend["longitude"]) for friend in friends) / len(friends)
        zoom_start = 2
    else:
        avg_lat = 20.0
        avg_lon = 0.0
        zoom_start = 2

    friends_map = folium.Map(
        location=[avg_lat, avg_lon],
        zoom_start=zoom_start,
        tiles="OpenStreetMap",
    )

    marker_cluster = MarkerCluster().add_to(friends_map)

    for friend in friends:
        notes = friend.get("notes") or ""
        popup_html = f"""
        <div style="min-width: 180px;">
            <strong>{friend.get("name", "")}</strong><br>
            {friend.get("city", "")}, {friend.get("country", "")}<br>
            <span>{notes}</span>
        </div>
        """

        folium.Marker(
            location=[
                float(friend["latitude"]),
                float(friend["longitude"]),
            ],
            tooltip=friend.get("name", ""),
            popup=folium.Popup(popup_html, max_width=300),
            icon=folium.Icon(icon="user", prefix="fa"),
        ).add_to(marker_cluster)

    return friends_map


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------
def friend_label(friend: dict[str, Any]) -> str:
    return (
        f'{friend.get("name", "")} — '
        f'{friend.get("city", "")}, {friend.get("country", "")}'
    )


def find_friend_by_id(
    friends: list[dict[str, Any]],
    friend_id: int,
) -> dict[str, Any] | None:
    return next(
        (friend for friend in friends if int(friend["id"]) == int(friend_id)),
        None,
    )


# ---------------------------------------------------------
# UI
# ---------------------------------------------------------
st.title("🌍 Friends Map")
st.caption("在世界地圖上記錄朋友所在的城市。")

try:
    friends = get_friends()
except Exception as exc:
    st.error("無法讀取 Supabase 資料。")
    st.exception(exc)
    st.stop()


with st.sidebar:
    st.header("新增朋友")

    with st.form("add_friend_form", clear_on_submit=True):
        new_name = st.text_input("姓名 *")
        new_city = st.text_input("城市 *")
        new_country = st.text_input("國家 *")
        new_notes = st.text_area("備註")

        add_submitted = st.form_submit_button(
            "新增朋友",
            use_container_width=True,
        )

    if add_submitted:
        if not new_name.strip() or not new_city.strip() or not new_country.strip():
            st.error("姓名、城市和國家都是必填欄位。")
        else:
            with st.spinner("正在尋找城市座標並新增資料..."):
                coordinates = geocode_city(new_city, new_country)

                if coordinates is None:
                    st.error("找不到這個城市，請檢查城市與國家的拼字。")
                else:
                    try:
                        latitude, longitude = coordinates
                        inserted = add_friend(
                            name=new_name,
                            city=new_city,
                            country=new_country,
                            latitude=latitude,
                            longitude=longitude,
                            notes=new_notes,
                        )
                        st.success(f'已新增 {inserted["name"]}！')
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as exc:
                        st.error("新增失敗。")
                        st.exception(exc)

    with st.expander("Supabase 診斷"):
        try:
            project_ref = (
                str(st.secrets["SUPABASE_URL"])
                .replace("https://", "")
                .split(".")[0]
            )
            st.write("目前連線專案：")
            st.code(project_ref)
            st.write(f"讀取到 {len(friends)} 筆資料")
        except Exception as exc:
            st.exception(exc)


search_term = st.text_input(
    "搜尋朋友、城市、國家或備註",
    placeholder="例如：Paris、Taiwan、Mary",
).strip().lower()

if search_term:
    filtered_friends = [
        friend
        for friend in friends
        if search_term
        in " ".join(
            [
                str(friend.get("name", "")),
                str(friend.get("city", "")),
                str(friend.get("country", "")),
                str(friend.get("notes", "")),
            ]
        ).lower()
    ]
else:
    filtered_friends = friends


map_column, list_column = st.columns([2, 1])

with map_column:
    st.subheader("朋友地圖")

    friends_map = create_map(filtered_friends)
    st_folium(
        friends_map,
        width=None,
        height=600,
        returned_objects=[],
        key="friends_map",
    )

with list_column:
    st.subheader(f"朋友列表（{len(filtered_friends)}）")

    if not filtered_friends:
        st.info("目前沒有符合條件的朋友。")
    else:
        for friend in filtered_friends:
            with st.expander(friend_label(friend)):
                if friend.get("notes"):
                    st.write(friend["notes"])
                else:
                    st.caption("沒有備註")

                st.caption(
                    f'座標：{float(friend["latitude"]):.4f}, '
                    f'{float(friend["longitude"]):.4f}'
                )


st.divider()
st.subheader("編輯或刪除朋友")

if not friends:
    st.info("新增朋友後，就可以在這裡編輯或刪除。")
else:
    friend_options = {
        friend_label(friend): int(friend["id"])
        for friend in friends
    }

    selected_label = st.selectbox(
        "選擇朋友",
        options=list(friend_options.keys()),
    )
    selected_id = friend_options[selected_label]
    selected_friend = find_friend_by_id(friends, selected_id)

    if selected_friend is not None:
        with st.form("edit_friend_form"):
            edit_name = st.text_input(
                "姓名",
                value=str(selected_friend.get("name", "")),
            )
            edit_city = st.text_input(
                "城市",
                value=str(selected_friend.get("city", "")),
            )
            edit_country = st.text_input(
                "國家",
                value=str(selected_friend.get("country", "")),
            )
            edit_notes = st.text_area(
                "備註",
                value=str(selected_friend.get("notes") or ""),
            )

            update_submitted = st.form_submit_button(
                "儲存修改",
                use_container_width=True,
            )

        if update_submitted:
            if not edit_name.strip() or not edit_city.strip() or not edit_country.strip():
                st.error("姓名、城市和國家都是必填欄位。")
            else:
                location_changed = (
                    edit_city.strip().lower()
                    != str(selected_friend.get("city", "")).strip().lower()
                    or edit_country.strip().lower()
                    != str(selected_friend.get("country", "")).strip().lower()
                )

                if location_changed:
                    with st.spinner("正在更新城市座標..."):
                        coordinates = geocode_city(edit_city, edit_country)
                else:
                    coordinates = (
                        float(selected_friend["latitude"]),
                        float(selected_friend["longitude"]),
                    )

                if coordinates is None:
                    st.error("找不到這個城市，請檢查拼字。")
                else:
                    try:
                        latitude, longitude = coordinates
                        update_friend(
                            friend_id=selected_id,
                            name=edit_name,
                            city=edit_city,
                            country=edit_country,
                            latitude=latitude,
                            longitude=longitude,
                            notes=edit_notes,
                        )
                        st.success("資料已更新。")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as exc:
                        st.error("更新失敗。")
                        st.exception(exc)

        delete_confirmed = st.checkbox(
            f'我確認要刪除「{selected_friend.get("name", "")}」',
            key=f"delete_confirm_{selected_id}",
        )

        if st.button(
            "刪除朋友",
            type="secondary",
            disabled=not delete_confirmed,
            use_container_width=True,
        ):
            try:
                delete_friend(selected_id)
                st.success("朋友已刪除。")
                st.cache_data.clear()
                st.rerun()
            except Exception as exc:
                st.error("刪除失敗。")
                st.exception(exc)
