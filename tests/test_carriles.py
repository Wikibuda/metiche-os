from __future__ import annotations

import unittest

from app.services import carriles
from app.services.dashboard_service import _plane_browse_url, _plane_seq


def _fila(
    seq: int,
    *,
    name: str = "",
    desc: str = "",
    state: str = "Todo",
    updated: str = "2026-10-05T12:00:00Z",
    labels: list[str] | None = None,
    priority: str | None = None,
) -> dict:
    """Fila con la forma que consume `carriles` (misma que el motor)."""
    return {
        "seq": seq,
        "name": name,
        "desc": desc,
        "state": state,
        "updated": updated,
        "labels": labels or [],
        "priority": priority,
    }


class CarrilesClasificacionTest(unittest.TestCase):
    def test_etiqueta_carril_explicita_gana(self) -> None:
        fila = _fila(1, name="cualquier cosa sin palabras clave", labels=["carril:roi"])
        self.assertEqual(carriles.carril_de(fila), "roi")

    def test_retorno_roi_decide_el_carril(self) -> None:
        self.assertEqual(carriles.carril_de(_fila(2, labels=["roi:ingreso"])), "negocio")
        self.assertEqual(carriles.carril_de(_fila(3, labels=["roi:ahorro"])), "roi")
        self.assertEqual(carriles.carril_de(_fila(4, labels=["roi:higiene"])), "operacion")

    def test_sin_pistas_cae_a_operacion(self) -> None:
        self.assertEqual(carriles.carril_de(_fila(5, name="zzz qqq")), "operacion")

    def test_clasificar_devuelve_motivo(self) -> None:
        carril, motivo = carriles.clasificar(_fila(6, labels=["roi:ingreso"]))
        self.assertEqual(carril, "negocio")
        self.assertTrue(str(motivo).strip())


class CarrilesAgruparTest(unittest.TestCase):
    def test_agrupar_trae_las_cuatro_pilas(self) -> None:
        agrupado = carriles.agrupar(
            [_fila(1, labels=["roi:ingreso"]), _fila(2, labels=["roi:ahorro"])]
        )
        self.assertEqual(set(agrupado.keys()), {"negocio", "roi", "operacion", "archivo"})
        self.assertEqual([f["seq"] for f in agrupado["negocio"]], [1])
        self.assertEqual([f["seq"] for f in agrupado["roi"]], [2])

    def test_cerradas_se_omiten_salvo_que_se_pidan(self) -> None:
        filas = [
            _fila(1, state="Done", labels=["roi:ingreso"]),
            _fila(2, state="Todo", labels=["roi:ahorro"]),
        ]
        abiertas = carriles.agrupar(filas, incluir_cerradas=False)
        self.assertEqual(abiertas["negocio"], [])
        self.assertEqual([f["seq"] for f in abiertas["roi"]], [2])
        todas = carriles.agrupar(filas, incluir_cerradas=True)
        self.assertEqual([f["seq"] for f in todas["negocio"]], [1])

    def test_lifo_dentro_del_carril(self) -> None:
        # El más nuevo (seq y fecha mayores) va primero dentro de su carril.
        filas = [
            _fila(10, updated="2026-10-01T00:00:00Z", labels=["roi:ahorro"]),
            _fila(11, updated="2026-10-04T00:00:00Z", labels=["roi:ahorro"]),
        ]
        agrupado = carriles.agrupar(filas)
        self.assertEqual([f["seq"] for f in agrupado["roi"]], [11, 10])

    def test_precedencia_negocio_antes_que_operacion(self) -> None:
        # `ordenar` respeta la precedencia fija negocio → roi → operacion → archivo.
        filas = [_fila(20, labels=["roi:higiene"]), _fila(21, labels=["roi:ingreso"])]
        orden = [f["seq"] for f in carriles.ordenar(filas)]
        self.assertEqual(orden, [21, 20])


class PlaneUrlTest(unittest.TestCase):
    def test_plane_seq_solo_para_tasks_de_plane(self) -> None:
        self.assertEqual(_plane_seq("plane-530"), 530)
        self.assertIsNone(_plane_seq("task-1"))
        self.assertIsNone(_plane_seq(None))

    def test_browse_url_en_formato_bueno(self) -> None:
        # El formato viejo /projects/<uuid>/issues/<uuid> salía roto; el bueno es /browse.
        url = _plane_browse_url(530)
        self.assertIsNotNone(url)
        assert url is not None  # para el type-checker
        self.assertTrue(url.endswith("/masa-madre-hq/browse/MASAM-530/"), url)
        self.assertNotIn("/projects/", url)


if __name__ == "__main__":
    unittest.main()
