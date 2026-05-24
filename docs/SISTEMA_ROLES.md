# Sistema de Roles — Metiche-OS

## Resumen

Metiche-OS implementa un sistema de roles para controlar quién puede ejecutar comandos
y lanzar enjambres desde Plane. Los roles se determinan por el email del autor del issue
o comentario en Plane.

## Tabla de Roles

| Rol     | Privilegios                               | Auto-ejecución                           |
|---------|-------------------------------------------|------------------------------------------|
| Admin   | Ejecución completa de comandos y enjambres | ✅ (salvo comandos `encolar` / `fifo`)    |
| Viewer  | Solo lectura                               | ❌                                        |

## ¿Cómo se determina el rol?

El sistema lee el `admin_ids` desde `app/core/roles.py`. Si el email del autor
coincide con algún email en `admin_ids`, el rol es `Admin`. De lo contrario, es `Viewer`.

```python
# app/core/roles.py

class RolesConfig:
    admin_ids: set[str] = {"gglunar@gmail.com", "gus@masamadremonterrey.com"}
```

## Comportamiento por componente

### `plane_bridge_service.py` (pull de issues `run:enjambre`)

Cuando un issue tiene la etiqueta `run:enjambre`:

- **Admin**: se lanza el enjambre automáticamente.
- **Viewer**: se agrega un comentario en el issue indicando que requiere aprobación
  de un Admin, y se marca como `pending_approval`. No se crea el enjambre.

### `plane_comment_watcher.py` (comandos `/metiche`)

Cuando alguien escribe un comentario con `/metiche accion=...`:

- **Admin**: el comando se ejecuta en su totalidad.
- **Viewer**: se agrega un comentario en el issue informando que no tiene permisos.
  El comando se omite.

### Excepción: `encolar` / `fifo`

Incluso los Admins no auto-ejecutan comandos que contengan "encolar" o "fifo"
en el nombre. Estos casos quedan pendientes de una revisión manual adicional.

## Cómo modificar los Admins

1. Abrir `app/core/roles.py`.
2. Editar el set `admin_ids`:

   ```python
   admin_ids: set[str] = {
       "email1@example.com",
       "email2@example.com",
       # Agregar más según sea necesario
   }
   ```

3. La propiedad `owner_display` se puede cambiar modificando `owner_name`:

   ```python
   owner_name: str = "Gus"
   ```

## Cómo agregar un nuevo rol

1. Agregar un método en `RolesConfig` (o extender `get_role`):

   ```python
   def get_role(self, author_email: str) -> str:
       author = (author_email or "").strip().lower()
       if author in {a.strip().lower() for a in self.admin_ids}:
           return "admin"
       # Nuevos roles:
       if author.endswith("@operador.metiche"):
           return "operator"
       return "viewer"
   ```

2. Actualizar `can_execute` según la lógica deseada para el nuevo rol.
3. Actualizar este documento con la tabla de roles actualizada.

## Notas

- Los emails se comparan en **minúsculas** y con `strip()` para evitar errores
  por espacios o mayúsculas.
- No hay herencia de roles: si no está en `admin_ids`, es `viewer`.
- El sistema de roles complementa el allowlist existente (`plane_command_author_allowlist`)
  pero no lo reemplaza.
