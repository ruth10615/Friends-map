import sqlite3
import time

import folium
import streamlit as st
from folium.plugins import MarkerCluster
from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim
from streamlit_folium import st_folium


DATABASE_FILE = "friends.db"


# --------------------------------------------------
# 資料庫
# --------------------------------------------------

def get_connection() -> sqlite3.Connection:
    """建立 SQLite 資料庫連線。"""
    connection = sqlite3.connect(
        DATABASE_FILE,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    return connection


def initialise_database() -> None:
    """建立朋友資料表。"""
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS friends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                city TEXT NOT NULL,
                country TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                notes TEXT DEFAULT ''
            )
            """
        )

        # 舊資料庫可能沒有 notes 欄位，因此自動補上
        columns = connection.execute(
            "PRAGMA table_info(friends)"
        ).fetchall()

        column_names = {
            column["name"]
            for column in columns
        }

        if "notes" not in column_names:
            connection.execute(
                """
                ALTER TABLE friends
                ADD COLUMN notes TEXT DEFAULT ''
                """
            )


def add_friend(
    name: str,
    city: str,
    country: str,
    latitude: float,
    longitude: float,
    notes: str,
) -> None:
    """新增朋友。"""
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO friends (
                name,
                city,
                country,
                latitude,
                longitude,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                city,
                country,
                latitude,
                longitude,
                notes,
            ),
        )


def get_friends(search_text: str = ""):
    """取得全部朋友，或依關鍵字搜尋。"""
    clean_search = search_text.strip()

    with get_connection() as connection:
        if clean_search:
            keyword = f"%{clean_search}%"

            return connection.execute(
                """
                SELECT
                    id,
                    name,
                    city,
                    country,
                    latitude,
                    longitude,
                    notes
                FROM friends
                WHERE
                    name LIKE ?
                    OR city LIKE ?
                    OR country LIKE ?
                    OR notes LIKE ?
                ORDER BY name COLLATE NOCASE
                """,
                (
                    keyword,
                    keyword,
                    keyword,
                    keyword,
                ),
            ).fetchall()

        return connection.execute(
            """
            SELECT
                id,
                name,
                city,
                country,
                latitude,
                longitude,
                notes
            FROM friends
            ORDER BY name COLLATE NOCASE
            """
        ).fetchall()


def get_friend(friend_id: int):
    """依 ID 取得單一朋友。"""
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT
                id,
                name,
                city,
                country,
                latitude,
                longitude,
                notes
            FROM friends
            WHERE id = ?
            """,
            (friend_id,),
        ).fetchone()


def update_friend(
    friend_id: int,
    name: str,
    city: str,
    country: str,
    latitude: float,
    longitude: float,
    notes: str,
) -> None:
    """更新朋友資料。"""
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE friends
            SET
                name = ?,
                city = ?,
                country = ?,
                latitude = ?,
                longitude = ?,
                notes = ?
            WHERE id = ?
            """,
            (
                name,
                city,
                country,
                latitude,
                longitude,
                notes,
                friend_id,
            ),
        )


def delete_friend(friend_id: int) -> None:
    """刪除朋友。"""
    with get_connection() as connection:
        connection.execute(
            """
            DELETE FROM friends
            WHERE id = ?
            """,
            (friend_id,),
        )


# --------------------------------------------------
# 城市定位
# --------------------------------------------------

@st.cache_data(ttl=86400, show_spinner=False)
def geocode_city(city: str, country: str):
    """將城市與國家轉換成經緯度。"""
    geolocator = Nominatim(
        user_agent="personal-friends-map-app"
    )

    search_text = f"{city}, {country}"

    try:
        location = geolocator.geocode(
            search_text,
            exactly_one=True,
            timeout=10,
        )
    except (GeocoderTimedOut, GeocoderServiceError):
        return None

    if location is None:
        return None

    return {
        "latitude": float(location.latitude),
        "longitude": float(location.longitude),
        "display_name": str(location.address),
    }


# --------------------------------------------------
# 地圖
# --------------------------------------------------

def create_map(friends):
    """建立朋友地圖。"""
    if friends:
        average_latitude = sum(
            float(friend["latitude"])
            for friend in friends
        ) / len(friends)

        average_longitude = sum(
            float(friend["longitude"])
            for friend in friends
        ) / len(friends)

        map_location = [
            average_latitude,
            average_longitude,
        ]

        zoom_start = 2 if len(friends) > 1 else 7
    else:
        map_location = [20, 0]
        zoom_start = 2

    friends_map = folium.Map(
        location=map_location,
        zoom_start=zoom_start,
        tiles="OpenStreetMap",
    )

    marker_cluster = MarkerCluster().add_to(
        friends_map
    )

    for friend in friends:
        notes = friend["notes"] or ""

        popup_content = f"""
        <div style="min-width: 180px;">
            <strong>{friend["name"]}</strong><br>
            {friend["city"]}, {friend["country"]}
        """

        if notes:
            popup_content += f"<br><br>{notes}"

        popup_content += "</div>"

        folium.Marker(
            location=[
                float(friend["latitude"]),
                float(friend["longitude"]),
            ],
            tooltip=str(friend["name"]),
            popup=folium.Popup(
                popup_content,
                max_width=300,
            ),
        ).add_to(marker_cluster)

    return friends_map


# --------------------------------------------------
# 頁面設定
# --------------------------------------------------

st.set_page_config(
    page_title="我的朋友地圖",
    page_icon="🌍",
    layout="wide",
)

initialise_database()

if "editing_friend_id" not in st.session_state:
    st.session_state.editing_friend_id = None

if "deleting_friend_id" not in st.session_state:
    st.session_state.deleting_friend_id = None


st.title("🌍 我的朋友地圖")
st.caption("記錄世界各地朋友居住的城市。")


# --------------------------------------------------
# 新增朋友
# --------------------------------------------------

with st.expander("➕ 加入朋友", expanded=False):
    with st.form(
        "add_friend_form",
        clear_on_submit=True,
    ):
        name = st.text_input(
            "朋友姓名",
            placeholder="例如：Marie",
        )

        col1, col2 = st.columns(2)

        with col1:
            city = st.text_input(
                "城市",
                placeholder="例如：Paris",
            )

        with col2:
            country = st.text_input(
                "國家或地區",
                placeholder="例如：France",
            )

        notes = st.text_area(
            "備註",
            placeholder="例如：大學同學、WhatsApp 聯絡",
        )

        submitted = st.form_submit_button(
            "搜尋城市並加入",
            use_container_width=True,
        )

        if submitted:
            clean_name = name.strip()
            clean_city = city.strip()
            clean_country = country.strip()
            clean_notes = notes.strip()

            if (
                not clean_name
                or not clean_city
                or not clean_country
            ):
                st.error(
                    "請填寫朋友姓名、城市和國家。"
                )
            else:
                with st.spinner(
                    "正在搜尋城市位置……"
                ):
                    location = geocode_city(
                        clean_city,
                        clean_country,
                    )

                if location is None:
                    st.error(
                        "找不到這個城市。"
                        "請檢查城市和國家名稱。"
                    )
                else:
                    add_friend(
                        name=clean_name,
                        city=clean_city,
                        country=clean_country,
                        latitude=location["latitude"],
                        longitude=location["longitude"],
                        notes=clean_notes,
                    )

                    st.success(
                        f"已加入 {clean_name}。"
                    )

                    time.sleep(0.5)
                    st.rerun()


# --------------------------------------------------
# 搜尋
# --------------------------------------------------

st.subheader("🔍 搜尋朋友")

search_text = st.text_input(
    "輸入姓名、城市、國家或備註",
    placeholder="例如：Marie、Paris、Japan",
    label_visibility="collapsed",
)

friends = get_friends(search_text)

if search_text:
    st.caption(
        f"找到 {len(friends)} 筆符合「{search_text}」的資料"
    )
else:
    st.caption(
        f"目前共有 {len(friends)} 位朋友"
    )


# --------------------------------------------------
# 地圖
# --------------------------------------------------

st.subheader("🗺️ 朋友地圖")

friends_map = create_map(friends)

st_folium(
    friends_map,
    height=550,
    use_container_width=True,
    key="friends-map",
)


# --------------------------------------------------
# 編輯表單
# --------------------------------------------------

if st.session_state.editing_friend_id is not None:
    editing_friend = get_friend(
        st.session_state.editing_friend_id
    )

    if editing_friend:
        st.divider()
        st.subheader(
            f"✏️ 編輯 {editing_friend['name']}"
        )

        with st.form("edit_friend_form"):
            edited_name = st.text_input(
                "朋友姓名",
                value=editing_friend["name"],
            )

            col1, col2 = st.columns(2)

            with col1:
                edited_city = st.text_input(
                    "城市",
                    value=editing_friend["city"],
                )

            with col2:
                edited_country = st.text_input(
                    "國家或地區",
                    value=editing_friend["country"],
                )

            edited_notes = st.text_area(
                "備註",
                value=editing_friend["notes"] or "",
            )

            save_col, cancel_col = st.columns(2)

            with save_col:
                save_edit = st.form_submit_button(
                    "儲存修改",
                    use_container_width=True,
                    type="primary",
                )

            with cancel_col:
                cancel_edit = st.form_submit_button(
                    "取消",
                    use_container_width=True,
                )

            if cancel_edit:
                st.session_state.editing_friend_id = None
                st.rerun()

            if save_edit:
                clean_name = edited_name.strip()
                clean_city = edited_city.strip()
                clean_country = edited_country.strip()
                clean_notes = edited_notes.strip()

                if (
                    not clean_name
                    or not clean_city
                    or not clean_country
                ):
                    st.error(
                        "姓名、城市和國家不能留空。"
                    )
                else:
                    city_changed = (
                        clean_city.lower()
                        != editing_friend["city"].lower()
                        or clean_country.lower()
                        != editing_friend["country"].lower()
                    )

                    if city_changed:
                        with st.spinner(
                            "正在更新城市位置……"
                        ):
                            location = geocode_city(
                                clean_city,
                                clean_country,
                            )

                        if location is None:
                            st.error(
                                "找不到新的城市位置，"
                                "請檢查城市和國家名稱。"
                            )
                            st.stop()

                        latitude = location["latitude"]
                        longitude = location["longitude"]
                    else:
                        latitude = float(
                            editing_friend["latitude"]
                        )
                        longitude = float(
                            editing_friend["longitude"]
                        )

                    update_friend(
                        friend_id=editing_friend["id"],
                        name=clean_name,
                        city=clean_city,
                        country=clean_country,
                        latitude=latitude,
                        longitude=longitude,
                        notes=clean_notes,
                    )

                    st.session_state.editing_friend_id = None
                    st.success("朋友資料已更新。")
                    time.sleep(0.5)
                    st.rerun()


# --------------------------------------------------
# 朋友名單
# --------------------------------------------------

st.divider()
st.subheader("👥 朋友名單")

if not friends:
    if search_text:
        st.info("沒有找到符合搜尋條件的朋友。")
    else:
        st.info("目前尚未加入朋友。")
else:
    for friend in friends:
        with st.container(border=True):
            info_col, edit_col, delete_col = st.columns(
                [5, 1, 1]
            )

            with info_col:
                st.markdown(
                    f"### {friend['name']}"
                )

                st.write(
                    f"📍 {friend['city']}, "
                    f"{friend['country']}"
                )

                if friend["notes"]:
                    st.caption(friend["notes"])

            with edit_col:
                if st.button(
                    "✏️ 編輯",
                    key=f"edit-{friend['id']}",
                    use_container_width=True,
                ):
                    st.session_state.editing_friend_id = (
                        friend["id"]
                    )
                    st.session_state.deleting_friend_id = None
                    st.rerun()

            with delete_col:
                if st.button(
                    "🗑️ 刪除",
                    key=f"delete-{friend['id']}",
                    use_container_width=True,
                ):
                    st.session_state.deleting_friend_id = (
                        friend["id"]
                    )
                    st.session_state.editing_friend_id = None
                    st.rerun()

            if (
                st.session_state.deleting_friend_id
                == friend["id"]
            ):
                st.warning(
                    f"確定要刪除 {friend['name']} 嗎？"
                )

                confirm_col, cancel_col = st.columns(2)

                with confirm_col:
                    if st.button(
                        "確認刪除",
                        key=f"confirm-delete-{friend['id']}",
                        type="primary",
                        use_container_width=True,
                    ):
                        delete_friend(friend["id"])
                        st.session_state.deleting_friend_id = None
                        st.success("朋友資料已刪除。")
                        time.sleep(0.5)
                        st.rerun()

                with cancel_col:
                    if st.button(
                        "取消",
                        key=f"cancel-delete-{friend['id']}",
                        use_container_width=True,
                    ):
                        st.session_state.deleting_friend_id = None
                        st.rerun()
