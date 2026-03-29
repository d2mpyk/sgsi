def test_unauthorized_access_redirects_to_login(client):
    """
    Verifica que un usuario sin cookies de sesión no pueda acceder a rutas protegidas.
    Debe ser redirigido al login (Código 303 o 307).
    """
    # Rutas críticas que deben estar protegidas
    protected_routes = [
        "/api/v1/dashboard/",  # Protegido por Middleware (Retorna 307 por defecto en RedirectResponse)
        "/api/v1/users",  # Protegido por Dependency get_current_admin (Retorna 303)
        "/api/v1/documents/view",  # Protegido por Dependency CurrentUser (Retorna 303)
    ]

    for route in protected_routes:
        # Realizamos la petición sin autenticarnos (client sin cookies)
        response = client.get(route, follow_redirects=False)

        # Validar redirección
        assert response.status_code in [
            303,
            307,
        ], f"Fallo de seguridad en {route}: Se esperaba redirección, se obtuvo {response.status_code}"

        # Validar que existe el header de destino
        assert "location" in response.headers
