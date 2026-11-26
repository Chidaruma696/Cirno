"""El documento que arma el usuario: una lista ordenada de páginas tomadas de uno o varios
PDF, con deshacer y rehacer. Sin Qt y sin tocar los archivos: solo el orden y los giros."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .render import Fuente

LIMITE_DESHACER = 100


@dataclass(frozen=True)
class Pagina:
    fuente: Fuente
    indice: int  # página dentro de la fuente, desde 0
    rotacion: int = 0  # giro añadido por el usuario, en grados horarios (0, 90, 180, 270)
    marcas: tuple = ()  # lo dibujado encima (ver `marcas.py`), en el espacio base de la página
    recorte: tuple[float, float, float, float] | None = None  # (x, y, ancho, alto) en el espacio base

    @property
    def tamano_base(self) -> tuple[float, float]:
        """El tamaño de la página entera tal como viene en el archivo."""
        return self.fuente.tamanos[self.indice]

    @property
    def zona(self) -> tuple[float, float, float, float]:
        """La parte de la página que queda a la vista: el recorte, o toda."""
        return self.recorte or (0.0, 0.0, *self.tamano_base)

    @property
    def tamano(self) -> tuple[float, float]:
        """El tamaño con el que se ve: recortada y girada."""
        _, _, ancho, alto = self.zona
        return (alto, ancho) if self.rotacion % 180 else (ancho, alto)

    @property
    def editada(self) -> bool:
        return bool(self.marcas) or self.recorte is not None

    @property
    def etiqueta(self) -> str:
        return f"{self.fuente.nombre} · {self.indice + 1}"


class Documento:
    def __init__(self) -> None:
        self.paginas: list[Pagina] = []
        self._deshacer: list[list[Pagina]] = []
        self._rehacer: list[list[Pagina]] = []
        self.modificado = False

    def __len__(self) -> int:
        return len(self.paginas)

    # ------------------------------------------------------------------ historial
    def _marcar(self) -> None:
        self._deshacer.append(list(self.paginas))
        del self._deshacer[:-LIMITE_DESHACER]
        self._rehacer.clear()
        self.modificado = True

    @property
    def puede_deshacer(self) -> bool:
        return bool(self._deshacer)

    @property
    def puede_rehacer(self) -> bool:
        return bool(self._rehacer)

    def deshacer(self) -> bool:
        if not self._deshacer:
            return False
        self._rehacer.append(self.paginas)
        self.paginas = self._deshacer.pop()
        self.modificado = True
        return True

    def rehacer(self) -> bool:
        if not self._rehacer:
            return False
        self._deshacer.append(self.paginas)
        self.paginas = self._rehacer.pop()
        self.modificado = True
        return True

    def fuentes(self) -> list[Fuente]:
        """Las fuentes que siguen en uso, contando las que el historial puede devolver."""
        vistas: dict[int, Fuente] = {}
        for lista in (self.paginas, *self._deshacer, *self._rehacer):
            for p in lista:
                vistas.setdefault(id(p.fuente), p.fuente)
        return list(vistas.values())

    # ------------------------------------------------------------------ operaciones
    @staticmethod
    def _limpias(filas, total: int) -> list[int]:
        return sorted({f for f in filas if 0 <= f < total})

    def agregar_fuente(self, fuente: Fuente, posicion: int | None = None) -> list[int]:
        return self.insertar([Pagina(fuente, i) for i in range(fuente.n_paginas)], posicion)

    def insertar(self, paginas: list[Pagina], posicion: int | None = None) -> list[int]:
        """Mete las páginas en `posicion` (al final si no se dice). Devuelve sus filas nuevas."""
        if not paginas:
            return []
        self._marcar()
        pos = len(self.paginas) if posicion is None else max(0, min(posicion, len(self.paginas)))
        self.paginas = self.paginas[:pos] + list(paginas) + self.paginas[pos:]
        return list(range(pos, pos + len(paginas)))

    def mover(self, filas, destino: int) -> list[int]:
        """Lleva las filas (conservando su orden entre sí) a quedar delante de la fila `destino`
        de la lista actual; `destino` = len(self) las manda al final. Devuelve sus filas nuevas."""
        filas = self._limpias(filas, len(self.paginas))
        if not filas:
            return []
        destino = max(0, min(destino, len(self.paginas)))
        movidas = [self.paginas[f] for f in filas]
        elegidas = set(filas)
        resto = [p for i, p in enumerate(self.paginas) if i not in elegidas]
        pos = destino - sum(1 for f in filas if f < destino)
        nueva = resto[:pos] + movidas + resto[pos:]
        nuevas_filas = list(range(pos, pos + len(movidas)))
        if all(a is b for a, b in zip(nueva, self.paginas)):
            return nuevas_filas
        self._marcar()
        self.paginas = nueva
        return nuevas_filas

    def eliminar(self, filas) -> int:
        filas = set(self._limpias(filas, len(self.paginas)))
        if not filas:
            return 0
        self._marcar()
        self.paginas = [p for i, p in enumerate(self.paginas) if i not in filas]
        return len(filas)

    def duplicar(self, filas) -> list[int]:
        """Copia las filas justo detrás de la última elegida. Devuelve las filas de las copias."""
        filas = self._limpias(filas, len(self.paginas))
        if not filas:
            return []
        return self.insertar([self.paginas[f] for f in filas], filas[-1] + 1)

    def rotar(self, filas, grados: int) -> None:
        filas = self._limpias(filas, len(self.paginas))
        if not filas or grados % 360 == 0:
            return
        self._marcar()
        self.paginas = list(self.paginas)
        for f in filas:
            p = self.paginas[f]
            self.paginas[f] = replace(p, rotacion=(p.rotacion + grados) % 360)

    def invertir(self, filas=None) -> None:
        """Invierte el orden de las filas elegidas entre sí (todas si no se dice cuáles)."""
        filas = self._limpias(filas if filas else range(len(self.paginas)), len(self.paginas))
        if len(filas) < 2:
            return
        self._marcar()
        self.paginas = list(self.paginas)
        for f, p in zip(filas, [self.paginas[f] for f in reversed(filas)]):
            self.paginas[f] = p

    def reemplazar(self, cambios: dict[int, Pagina]) -> None:
        """Cambia varias páginas de una vez (lo que sale del editor, numerar, marca de agua): un solo paso de deshacer."""
        cambios = {f: p for f, p in cambios.items() if 0 <= f < len(self.paginas) and p != self.paginas[f]}
        if not cambios:
            return
        self._marcar()
        self.paginas = list(self.paginas)
        for f, p in cambios.items():
            self.paginas[f] = p

    def intercalar(self, segunda_al_reves: bool = False) -> None:
        """Mezcla la primera mitad con la segunda, una y una: para lo que se escaneó primero por las
        caras y luego por los dorsos. Con `segunda_al_reves`, los dorsos vienen del último al primero
        (lo normal al dar la vuelta al montón)."""
        n = len(self.paginas)
        if n < 2:
            return
        mitad = (n + 1) // 2
        caras, dorsos = self.paginas[:mitad], self.paginas[mitad:]
        if segunda_al_reves:
            dorsos = dorsos[::-1]
        nueva = []
        for i, cara in enumerate(caras):
            nueva.append(cara)
            if i < len(dorsos):
                nueva.append(dorsos[i])
        self._marcar()
        self.paginas = nueva

    def vaciar(self) -> None:
        if self.paginas:
            self._marcar()
            self.paginas = []
