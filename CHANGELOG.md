# Changelog

## 2026-06-08

### Fixed

- Robustecido el bridge de Plane para que los issues directos se creen con autor admin valido.
- Endurecida la idempotencia del bridge para evitar relanzamientos de swarm por cambios cosmeticos o solo de `updated_at`.

### Changed

- Documentado el modelo canonico `Task != Swarm` para separar semaforo del bridge y ejecucion real del enjambre.
- Institucionalizado `CHANNEL_TARGETS` como decision estable de routing.
- Estandarizada la salida consolidada del enjambre mediante `compiled_message`.
- Agregado `metiche@masamadremonterrey.com` a `admin_ids` como identidad operativa autorizada.

### Chore

- Agregados a `.gitignore` los archivos operativos generados:
  - `data/openclaw-autoreply-state.json`
  - `projections/bitacora/bitacora_de_asombros.md`

### Commits

- `4b4ddd6` `fix: robustecer bridge de plane y documentar flujo war room`
- `ec7b9cd` `feat: grant Metiche admin access and standardize swarm output routing`
- `fd10d9b` `chore: ignore generated operational state files`
