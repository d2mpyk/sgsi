# Checklist de Instalación SGSI en CentOS 10 con Apache

Este checklist asume que en el servidor ya conviven:
- `BookStack` en `/bookstack`
- `metrics` en `/metrics`
- y se agregará `SGSI` en `/sgsi` con backend FastAPI en `127.0.0.1:9000`.

## 1. Instalar dependencias base

```bash
sudo dnf update -y
sudo dnf install -y httpd python3 python3-pip python3-virtualenv git policycoreutils-python-utils
```

## 2. Desplegar código en servidor

```bash
sudo mkdir -p /var/www/html/sgsi
sudo chown -R $USER:$USER /var/www/html/sgsi
```

Copiar el proyecto en `/var/www/html/sgsi` (por `git clone`, `rsync`, etc.).

## 3. Crear entorno virtual e instalar requerimientos

```bash
cd /var/www/html/sgsi
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Configurar variables de entorno

```bash
cp .env_example .env
```

Completar variables obligatorias (DB, JWT, SMTP, admin bootstrap, etc.) y asegurar:

```env
ROOT_PATH=/sgsi
```

## 5. Preparar permisos de carpetas estáticas/media

```bash
mkdir -p /var/www/html/sgsi/media/documents/certificates
mkdir -p /var/www/html/sgsi/media/profile_pics
sudo chown -R apache:apache /var/www/html/sgsi/media
sudo chown -R apache:apache /var/www/html/sgsi/static
```

## 6. Crear servicio systemd de SGSI (Uvicorn puerto 9000)

Archivo: `/etc/systemd/system/sgsi.service`

```ini
[Unit]
Description=SGSI FastAPI (Uvicorn)
After=network.target

[Service]
User=apache
Group=apache
WorkingDirectory=/var/www/html/sgsi
Environment="ROOT_PATH=/sgsi"
ExecStart=/var/www/html/sgsi/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 9000 --workers 2
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Activar servicio:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now sgsi
sudo systemctl status sgsi
```

## 7. Configurar Apache (httpd.conf) con BookStack + metrics + SGSI

Usar el archivo `httpd.conf` fusionado incluido en este proyecto.

Puntos clave:
- Redirección raíz `/` hacia `/bookstack/`
- Proxy de `/metrics/` hacia `127.0.0.1:8000`
- Proxy de `/sgsi/` hacia `127.0.0.1:9000`
- Exclusión y alias para `/metrics/static`, `/metrics/media`, `/sgsi/static`, `/sgsi/media`

## 8. Verificar módulos Apache requeridos

```bash
sudo apachectl -M | egrep "proxy|proxy_http|rewrite|headers"
```

Debe existir al menos:
- `proxy_module`
- `proxy_http_module`
- `rewrite_module`

## 9. Validar configuración y reiniciar Apache

```bash
sudo apachectl configtest
sudo systemctl restart httpd
sudo systemctl status httpd
```

## 10. Ajuste SELinux para proxy a backend local

```bash
sudo setsebool -P httpd_can_network_connect 1
```

## 11. Pruebas finales

```bash
curl -I http://127.0.0.1:9000/sgsi/api/v1/auth/login
curl -I http://192.168.1.20/sgsi/api/v1/auth/login
```

Verificar también en navegador:
- `http://192.168.1.20/bookstack/`
- `http://192.168.1.20/metrics/`
- `http://192.168.1.20/sgsi/api/v1/auth/login`

## 12. Logs útiles de diagnóstico

```bash
sudo journalctl -u sgsi -f
sudo tail -f /var/log/httpd/192.168.1.20_error.log
sudo tail -f /var/log/httpd/192.168.1.20_access.log
```

Si algo Falla
# 1) Etiquetar el venv como ejecutable de usuario, no como contenido web
sudo semanage fcontext -a -t usr_t '/var/www/html/sgsi/.venv(/.*)?'
sudo restorecon -Rv /var/www/html/sgsi/.venv

# 2) Verifica contexto
ls -lZ /var/www/html/sgsi/.venv/bin/python

# 3) Reinicia servicio
sudo systemctl daemon-reload
sudo systemctl restart sgsi
sudo systemctl status sgsi -l --no-pager

Si semanage dice que ya existe una regla, usa:

sudo semanage fcontext -m -t usr_t '/var/www/html/sgsi/.venv(/.*)?'
sudo restorecon -Rv /var/www/html/sgsi/.venv
