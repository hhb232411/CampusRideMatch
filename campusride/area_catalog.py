"""Bilingual fixed areas used by trip publishing and search."""


# These entries replace original English-only labels while preserving IDs
# in an existing development database. The remaining entries are inserted.
AREA_RENAMES = {
    "Kowloon Tong": "Kowloon Tong 九龙塘",
    "Mong Kok": "Mong Kok 旺角",
    "Tsim Sha Tsui": "Tsim Sha Tsui 尖沙咀",
    "Central": "Central 中环",
    "Causeway Bay": "Causeway Bay 铜锣湾",
    "Sha Tin": "Sha Tin 沙田",
    "Tai Po": "Tai Po 大埔",
    "Tseung Kwan O": "Tseung Kwan O 将军澳",
}


RETIRED_UNIVERSITY_LABELS = (
    "City University",
    "Hong Kong University",
    "City University of Hong Kong (CityU) 香港城市大学",
    "The University of Hong Kong (HKU) 香港大学",
    "The Chinese University of Hong Kong (CUHK) 香港中文大学",
    "Hong Kong University of Science and Technology (HKUST) 香港科技大学",
    "The Hong Kong Polytechnic University (PolyU) 香港理工大学",
    "Hong Kong Baptist University (HKBU) 香港浸会大学",
    "Lingnan University (LU) 岭南大学",
    "The Education University of Hong Kong (EdUHK) 香港教育大学",
    "Hong Kong Metropolitan University (HKMU) 香港都会大学",
    "Hong Kong Shue Yan University (HKSYU) 香港树仁大学",
    "The Hang Seng University of Hong Kong (HSUHK) 香港恒生大学",
    "Saint Francis University (SFU) 圣方济各大学",
    "Chu Hai College of Higher Education 珠海学院",
    "Hong Kong Academy for Performing Arts (HKAPA) 香港演艺学院",
    "Hong Kong Institute of Vocational Education (IVE) 香港专业教育学院",
    "Technological and Higher Education Institute (THEi) 香港高等教育科技学院",
)


AREA_NAMES = tuple(AREA_RENAMES.values()) + (
    # Hong Kong Island
    "Admiralty 金钟",
    "Wan Chai 湾仔",
    "North Point 北角",
    "Quarry Bay 鲗鱼涌",
    "Chai Wan 柴湾",
    "Kennedy Town 坚尼地城",
    "Pok Fu Lam 薄扶林",
    "Braemar Hill 宝马山",
    "Aberdeen 香港仔",
    # Kowloon
    "Hung Hom 红磡",
    "Jordan 佐敦",
    "Yau Ma Tei 油麻地",
    "Sham Shui Po 深水埗",
    "Mei Foo 美孚",
    "Diamond Hill 钻石山",
    "Wong Tai Sin 黄大仙",
    "Kwun Tong 观塘",
    "Ho Man Tin 何文田",
    # New Territories and islands
    "Tsuen Wan 荃湾",
    "Kwai Fong 葵芳",
    "Tai Wai 大围",
    "Fo Tan 火炭",
    "University Station 大学站",
    "Siu Lek Yuen 小沥源",
    "Ma On Shan 马鞍山",
    "Fanling 粉岭",
    "Sheung Shui 上水",
    "Tuen Mun 屯门",
    "Yuen Long 元朗",
    "Tin Shui Wai 天水围",
    "Hang Hau 坑口",
    "Clear Water Bay 清水湾",
    "Tung Chung 东涌",
    "Hong Kong International Airport 香港国际机场",
)


def sync_location_areas(connection):
    """Add/rename catalog rows without deleting trips or user data."""
    for old_name, bilingual_name in AREA_RENAMES.items():
        connection.execute(
            "UPDATE location_areas SET name = ? WHERE name = ?",
            (bilingual_name, old_name),
        )
    connection.executemany(
        "UPDATE location_areas SET is_active = 0 WHERE name = ?",
        ((name,) for name in RETIRED_UNIVERSITY_LABELS),
    )
    connection.executemany(
        "INSERT OR IGNORE INTO location_areas (name) VALUES (?)",
        ((name,) for name in AREA_NAMES),
    )
