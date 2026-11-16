"""
test_chats.py - Saved chat sessions: /chats (list, get, save). Uses the fake chat store.
"""

OWNER = {"X-Chat-Owner": "owner-aaaa-1111"}
OTHER = {"X-Chat-Owner": "owner-bbbb-2222"}
SESSION = "session-0001-abcd"


def session_body(name="What were the revenue", messages=None):
    return {
        "name": name,
        "renamed": False,
        "company": "MSFT",
        "messages": messages if messages is not None else [
            {"role": "user", "text": "What were the revenue for the quarter?", "company": "MSFT"},
            {"role": "assistant", "text": "Revenue was $92.3 billion [S1].", "company": "MSFT",
             "sources": [{"ref": "S1", "file_name": "MSFT-PressReleaseFY27q1.docx"}]},
        ],
    }


def test_a_saved_session_is_listed_for_its_owner_with_its_name(client):
    assert client.put(f"/chats/{SESSION}", json=session_body(), headers=OWNER).status_code == 200

    listed = client.get("/chats", headers=OWNER).json()
    assert [s["id"] for s in listed] == [SESSION]
    assert listed[0]["name"] == "What were the revenue"
    assert listed[0]["company"] == "MSFT"
    assert "messages" not in listed[0]           # the list is light: messages come from GET /chats/{id}


def test_get_returns_the_messages_and_sources(client):
    client.put(f"/chats/{SESSION}", json=session_body(), headers=OWNER)

    found = client.get(f"/chats/{SESSION}", headers=OWNER).json()
    assert found["messages"][1]["text"] == "Revenue was $92.3 billion [S1]."
    assert found["messages"][1]["sources"][0]["ref"] == "S1"


def test_unknown_session_is_404(client):
    assert client.get("/chats/no-such-session", headers=OWNER).status_code == 404


def test_each_owner_sees_only_their_own_sessions(client):
    client.put(f"/chats/{SESSION}", json=session_body(), headers=OWNER)

    assert client.get("/chats", headers=OTHER).json() == []
    assert client.get(f"/chats/{SESSION}", headers=OTHER).status_code == 404


def test_saving_again_replaces_the_name_and_messages(client):
    client.put(f"/chats/{SESSION}", json=session_body(), headers=OWNER)
    renamed = session_body(name="Q1 revenue check", messages=[])
    renamed["renamed"] = True
    client.put(f"/chats/{SESSION}", json=renamed, headers=OWNER)

    found = client.get(f"/chats/{SESSION}", headers=OWNER).json()
    assert found["name"] == "Q1 revenue check"
    assert found["renamed"] is True
    assert found["messages"] == []
    assert len(client.get("/chats", headers=OWNER).json()) == 1      # same session, not a copy


def test_a_missing_or_short_owner_is_refused(client):
    assert client.get("/chats").status_code == 400
    assert client.get("/chats", headers={"X-Chat-Owner": "short"}).status_code == 400
    assert client.put(f"/chats/{SESSION}", json=session_body()).status_code == 400


def test_a_bad_session_id_is_refused(client):
    assert client.get("/chats/bad_id!", headers=OWNER).status_code == 400


def test_a_message_with_an_unknown_role_is_refused(client):
    body = session_body(messages=[{"role": "system", "text": "hi", "company": "MSFT"}])
    assert client.put(f"/chats/{SESSION}", json=body, headers=OWNER).status_code == 422


def test_too_many_messages_are_refused(client):
    body = session_body(messages=[{"role": "user", "text": "q", "company": "MSFT"}] * 201)
    assert client.put(f"/chats/{SESSION}", json=body, headers=OWNER).status_code == 422


def test_a_name_longer_than_60_characters_is_refused(client):
    assert client.put(f"/chats/{SESSION}", json=session_body(name="x" * 61), headers=OWNER).status_code == 422


def test_delete_removes_the_session_for_its_owner_only(client):
    client.put(f"/chats/{SESSION}", json=session_body(), headers=OWNER)

    assert client.delete(f"/chats/{SESSION}", headers=OTHER).status_code == 404   # another browser cannot delete it
    assert client.get(f"/chats/{SESSION}", headers=OWNER).status_code == 200

    assert client.delete(f"/chats/{SESSION}", headers=OWNER).json() == {"id": SESSION, "deleted": True}
    assert client.get(f"/chats/{SESSION}", headers=OWNER).status_code == 404
    assert client.get("/chats", headers=OWNER).json() == []


def test_deleting_twice_is_404(client):
    client.put(f"/chats/{SESSION}", json=session_body(), headers=OWNER)
    client.delete(f"/chats/{SESSION}", headers=OWNER)

    assert client.delete(f"/chats/{SESSION}", headers=OWNER).status_code == 404
