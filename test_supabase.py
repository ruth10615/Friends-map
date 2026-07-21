import tomllib

from supabase import create_client


with open(
    ".streamlit/secrets.toml",
    "rb",
) as file:
    secrets = tomllib.load(file)


supabase = create_client(
    secrets["SUPABASE_URL"],
    secrets["SUPABASE_KEY"],
)


try:
    insert_response = (
        supabase
        .table("friends")
        .insert(
            {
                "name": "Supabase Test",
                "city": "Paris",
                "country": "France",
                "latitude": 48.8566,
                "longitude": 2.3522,
                "notes": "連線測試，可稍後刪除",
            }
        )
        .execute()
    )

    print("新增結果：")
    print(insert_response.data)

    select_response = (
        supabase
        .table("friends")
        .select("*")
        .execute()
    )

    print("\n讀取結果：")
    print(select_response.data)

except Exception as error:
    print("\n測試失敗：")
    print(type(error).__name__)
    print(error)
