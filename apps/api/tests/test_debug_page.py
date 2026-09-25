def test_debug_page_contains_workflow_controls(client):
    response = client.get("/debug")

    assert response.status_code == 200
    assert "Создать диалог" in response.text
    assert "Не помогло" in response.text
    assert "Передать специалисту" in response.text
    assert "Debug JSON" in response.text
