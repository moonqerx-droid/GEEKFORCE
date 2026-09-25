def test_operator_debug_page_contains_queue(client):
    response = client.get("/debug/operator")

    assert response.status_code == 200
    assert "Очередь специалиста" in response.text
    assert "Обновить очередь" in response.text
    assert "/api/operator/tickets" in response.text
