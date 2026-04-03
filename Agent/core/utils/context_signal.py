import datetime


def get_time_context() -> dict[str, str]:
    hour = datetime.datetime.now().hour
    if 5 <= hour < 9:
        period, mood = "morning", "energetic"
    elif 9 <= hour < 13:
        period, mood = "work", "focused"
    elif 13 <= hour < 17:
        period, mood = "afternoon", "relaxed"
    elif 17 <= hour < 21:
        period, mood = "evening", "calm"
    else:
        period, mood = "night", "sleep"
    return {"period": period, "mood": mood}


def get_music_query(genre: str) -> str:
    context = get_time_context()
    genre_text = str(genre or "").strip()
    if not genre_text:
        return context["mood"]
    return f"{genre_text} {context['mood']}"
