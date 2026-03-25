# 🌸 Sakura Workspace - Asistente Personal Zen

**Gateway independiente** para proyectos creativos y personales de Gus.

## 🚀 Inicio Rápido

```bash
# Navega al workspace
cd ~/.openclaw/workspace-personal

# Inicia el gateway
./sakura-start.sh

# Ver estado
./sakura-status.sh

# Detener
./sakura-stop.sh
```

## 📁 Estructura

```
~/.openclaw/workspace-personal/
├── SOUL.md              # Identidad Zen del asistente (Sakura)
├── USER.md              # Contexto sobre Gus
├── INDEX.md             # Índice de proyectos accesibles
├── memory/              # Diario de interacciones (crear si necesario)
├── links/               # Symlinks a proyectos personales
│   └── faro-cuantico -> ~/faro_cuantico_completo
└── scripts/
    ├── sakura-start.sh   # Iniciar gateway
    ├── sakura-stop.sh    # Detener gateway
    └── sakura-status.sh  # Ver estado

~/.openclaw-personal/     # Datos y configuración del gateway
├── openclaw.json        # Configuración minimalista
└── sakura.log          # Logs del gateway
```

## 🔗 Proyectos Accesibles

### 🌌 Faro Cuántico
**Ruta:** `links/faro-cuantico/`
**Contenido:** Proyecto literario/filosófico completo

**Archivos importantes:**
- `ESTATUS.md` - Estado actual del proyecto
- `SISTEMA_COMPLETO_INTEGRADO.md` - Arquitectura completa
- `uploads/ya-en-faro-cuantico/` - Historias completas
- `hijos_amor/` - Subproyectos relacionados

### 📓 Otros Proyectos
Para agregar más proyectos, crea symlinks en `links/`:

```bash
cd ~/.openclaw/workspace-personal/links
ln -s ~/ruta/a/tu/proyecto nombre-del-proyecto
```

## 🧠 Cómo Usar el Gateway

1. **Inicia Sakura Gateway:** `./sakura-start.sh`
2. **Accede via HTTP:** http://localhost:18800
3. **Usa herramientas básicas:**
   - Leer archivos: `read links/faro-cuantico/ESTATUS.md`
   - Listar contenido: `exec ls -la links/faro-cuantico/`
   - Buscar archivos: `exec find links/ -name "*.md"`

## ⚙️ Configuración Técnica

- **Puerto:** 18800 (aislado de gateways de negocio)
- **Modelo:** Claude 3.5 Haiku (rápido y poético)
- **Workspace:** `~/.openclaw/workspace-personal`
- **Datos:** `~/.openclaw-personal` (completamente separado)
- **Plugins habilitados:** files, web, calendar, exec (limitado)

## 🎯 Propósito

Este gateway es para:
- ✅ **Proyectos personales y creativos**
- ✅ **Exploración de archivos .md**
- ✅ **Organización tranquila**
- ❌ **Negocios (usar gateway de Masa Madre)**
- ❌ **Operaciones empresariales**

---

_Como los cerezos, este espacio florece con uso tranquilo y atención plena._
