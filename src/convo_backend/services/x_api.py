import requests
import os

from dotenv import load_dotenv

load_dotenv()


async def get_x_spaces(query: str):
    url = f"https://api.x.com/2/spaces/search?query={query}&state=live&expansions=host_ids,speaker_ids,topic_ids&space.fields=lang"
    headers = {"Authorization": f"Bearer {os.environ['X_API_BEARER_TOKEN']}"}
    response = requests.get(url, headers=headers)
    return response.json()


def parse_x_spaces(api_response: dict, only_english: bool = True):
    api_response = api_response.copy()
    parsed_spaces = []
    if not api_response.get("data"):
        return []
    for space in api_response["data"]:
        if only_english and space["lang"] != "en":
            continue
        parsed_space = {}
        # parse user info
        parsed_space["speakers"] = []
        parsed_space["hosts"] = []
        for user in api_response["includes"]["users"]:
            if space.get("speaker_ids") and user["id"] in space["speaker_ids"]:
                parsed_space["speakers"].append(user)
            if user["id"] in space["host_ids"]:
                parsed_space["hosts"].append(user)

        # parse topic info
        parsed_space["topics"] = []
        for topic in api_response["includes"].get("topics", []):
            if space.get("topic_ids") and topic["id"] in space["topic_ids"]:
                parsed_space["topics"].append(topic)

        parsed_space["space_id"] = space["id"]
        parsed_spaces.append(parsed_space)

    return parsed_spaces


def get_space_by_id(spaces: list, space_id: str):
    for space in spaces:
        if space["space_id"] == space_id:
            return space
    return None


def construct_x_api_url(space_id: str):
    return f"https://x.com/i/spaces/{space_id}"
