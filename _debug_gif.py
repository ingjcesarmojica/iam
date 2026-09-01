"""Diagnostica por que el GIF del avatar no se ve en el front."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import app


# 1) Verificar que el archivo existe y es GIF valido
print("=" * 70)
print("[1] Archivo GIF en disco:")
print("=" * 70)
gif_path = os.path.join(os.path.dirname(__file__), "interfaz.gif")
print(f"  Ruta: {gif_path}")
print(f"  Existe: {os.path.exists(gif_path)}")
if os.path.exists(gif_path):
    size = os.path.getsize(gif_path)
    with open(gif_path, "rb") as f:
        header = f.read(20)
    print(f"  Tamano: {size} bytes")
    print(f"  Header hex: {header.hex()}")
    print(f"  Signature GIF: {header[:6].decode('ascii', errors='replace')}")
    # Dimensiones del GIF
    import struct
    width = struct.unpack('<H', header[6:8])[0]
    height = struct.unpack('<H', header[8:10])[0]
    print(f"  Dimensiones: {width} x {height} px")
print()

# 2) Verificar que el backend lo sirve
print("=" * 70)
print("[2] Backend sirve /interfaz.gif:")
print("=" * 70)
with app.app.test_client() as client:
    r = client.get("/interfaz.gif")
    print(f"  Status: {r.status_code}")
    print(f"  Content-Type: {r.content_type}")
    print(f"  Content-Length: {r.content_length}")
    print(f"  Cache-Control: {r.headers.get('Cache-Control')}")
    print(f"  ETag: {r.headers.get('ETag')}")
    print(f"  Tamano respuesta: {len(r.data)} bytes")
    # Verificar que la primera parte es GIF
    sig = r.data[:6].decode('ascii', errors='replace')
    print(f"  Signature: {sig}")
print()

# 3) Verificar el HTML que llega al navegador
print("=" * 70)
print("[3] HTML que llega al navegador:")
print("=" * 70)
with app.app.test_client() as client:
    r = client.get("/")
    html = r.data.decode('utf-8', errors='replace')

# Buscar el bloque del avatar
import re
match = re.search(r'<div class="avatar-container">.*?</div>\s*</div>\s*</div>', html, re.DOTALL)
if match:
    print("  Bloque avatar-container en HTML:")
    for line in match.group(0).split('\n'):
        print(f"    {line}")
print()

# 4) Verificar el CSS relevante
print("=" * 70)
print("[4] CSS del avatar en HTML:")
print("=" * 70)
# Extraer todos los selectores relacionados con avatar
for selector in ['.avatar-container', '.avatar ', '.avatar img', '.avatar::before', '.avatar.avatar--idle']:
    idx = html.find(selector + ' {')
    if idx > 0:
        # Extraer hasta la siguiente llave de cierre
        end = html.find('}', idx)
        css_block = html[idx:end + 1]
        print(f"  {selector} {{ ... }}")
        for ln in css_block.split('\n')[:15]:
            print(f"    {ln.strip()}")
        print()
print()

# 5) Verificar que no haya elementos que tapen el avatar
print("=" * 70)
print("[5] Posibles elementos que tapen el avatar:")
print("=" * 70)
# Buscar pulse-rings, online-badge
for selector in ['.pulse-rings', '.online-badge', '.avatar::before']:
    cnt = html.count(selector + ' {')
    print(f"  {selector}: {cnt} definiciones de estilo")
print()

# 6) Verificar el z-index del avatar
print("=" * 70)
print("[6] z-index del avatar y elementos cercanos:")
print("=" * 70)
for line in html.split('\n'):
    if 'z-index' in line and ('avatar' in line.lower() or 'pulse' in line.lower() or 'online' in line.lower()):
        print(f"  {line.strip()}")