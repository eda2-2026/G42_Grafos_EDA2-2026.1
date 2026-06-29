import os
import cv2
import h5py
import numpy as np
from collections import deque


PASTA_ENTRADA = "h5_files"
PASTA_SAIDA = "outputs_flood_fill"

EXTENSOES_VALIDAS = (".h5",)

ID_FILTRAR = 8
AREA_MINIMA = 20
CONECTIVIDADE = 8

GAP_MAXIMO_PIXELS = 25
SOBREPOSICAO_VERTICAL_MINIMA = 0.25

VERMELHO = (0, 0, 255)
VERDE = (0, 255, 0)


class GrafoDePixels:
    def __init__(self, mascara, conectividade=8):
        self.mascara = mascara
        self.altura, self.largura = mascara.shape

        if conectividade == 4:
            self.direcoes = [
                (-1, 0),
                (1, 0),
                (0, -1),
                (0, 1)
            ]
        else:
            self.direcoes = [
                (-1, 0),
                (1, 0),
                (0, -1),
                (0, 1),
                (-1, -1),
                (-1, 1),
                (1, -1),
                (1, 1)
            ]

    def pixel_valido(self, x, y):
        if x < 0 or x >= self.largura:
            return False

        if y < 0 or y >= self.altura:
            return False

        return self.mascara[y, x] > 0

    def vizinhos(self, x, y):
        for dx, dy in self.direcoes:
            novo_x = x + dx
            novo_y = y + dy

            if self.pixel_valido(novo_x, novo_y):
                yield novo_x, novo_y


def carregar_arquivos_h5_da_pasta(pasta):
    arquivos = []

    for nome_arquivo in sorted(os.listdir(pasta)):
        if nome_arquivo.lower().endswith(EXTENSOES_VALIDAS):
            arquivos.append(os.path.join(pasta, nome_arquivo))

    return arquivos


def carregar_labels_h5(caminho_h5):
    with h5py.File(caminho_h5, "r") as arquivo:
        if "labels" not in arquivo:
            raise ValueError(
                f"O arquivo HDF5 '{caminho_h5}' não contém o dataset 'labels'."
            )

        labels = arquivo["labels"][:]

    labels = np.array(labels)

    if labels.ndim == 3:
        labels = np.squeeze(labels)

        if labels.ndim == 3:
            labels = labels[:, :, 0]

    return labels


def carregar_imagem_associada(caminho_h5):
    pasta_h5 = os.path.dirname(caminho_h5)
    nome_base, _ = os.path.splitext(os.path.basename(caminho_h5))

    extensoes = [".png", ".jpg", ".jpeg", ".bmp", ".webp"]

    for extensao in extensoes:
        caminho = os.path.join(pasta_h5, nome_base + extensao)

        if os.path.exists(caminho):
            imagem = cv2.imread(caminho)

            if imagem is not None:
                return imagem

    if os.path.exists("images"):
        for extensao in extensoes:
            caminho = os.path.join("images", nome_base + extensao)

            if os.path.exists(caminho):
                imagem = cv2.imread(caminho)

                if imagem is not None:
                    return imagem

    return None


def filtrar_id(labels, id_alvo):
    mascara = np.zeros_like(labels, dtype=np.uint8)
    mascara[labels == id_alvo] = 255
    return mascara


def flood_fill_bfs(grafo, x_inicial, y_inicial, visitados):
    fila = deque()
    componente = []

    fila.append((x_inicial, y_inicial))
    visitados[y_inicial, x_inicial] = True

    while fila:
        x, y = fila.popleft()
        componente.append((x, y))

        for vizinho_x, vizinho_y in grafo.vizinhos(x, y):
            if not visitados[vizinho_y, vizinho_x]:
                visitados[vizinho_y, vizinho_x] = True
                fila.append((vizinho_x, vizinho_y))

    return componente


def encontrar_componentes_conectados(mascara):
    grafo = GrafoDePixels(mascara, conectividade=CONECTIVIDADE)
    visitados = np.zeros_like(mascara, dtype=bool)

    componentes = []

    for y in range(grafo.altura):
        for x in range(grafo.largura):
            if grafo.pixel_valido(x, y) and not visitados[y, x]:
                componente = flood_fill_bfs(grafo, x, y, visitados)

                if len(componente) >= AREA_MINIMA:
                    componentes.append(componente)

    return componentes


def calcular_info_componente(componente):
    xs = [p[0] for p in componente]
    ys = [p[1] for p in componente]

    x_min = min(xs)
    x_max = max(xs)
    y_min = min(ys)
    y_max = max(ys)

    largura = x_max - x_min + 1
    altura = y_max - y_min + 1

    return {
        "area": len(componente),
        "x_min": x_min,
        "x_max": x_max,
        "y_min": y_min,
        "y_max": y_max,
        "largura": largura,
        "altura": altura,
        "centro_x": sum(xs) / len(xs),
        "centro_y": sum(ys) / len(ys)
    }


def calcular_gap_horizontal(info_a, info_b):
    if info_a["x_max"] < info_b["x_min"]:
        return info_b["x_min"] - info_a["x_max"] - 1

    if info_b["x_max"] < info_a["x_min"]:
        return info_a["x_min"] - info_b["x_max"] - 1

    return 0


def calcular_sobreposicao_vertical(info_a, info_b):
    topo = max(info_a["y_min"], info_b["y_min"])
    base = min(info_a["y_max"], info_b["y_max"])

    sobreposicao = max(0, base - topo + 1)

    menor_altura = min(info_a["altura"], info_b["altura"])

    if menor_altura == 0:
        return 0

    return sobreposicao / menor_altura


def existe_espaco_pequeno_no_meio(info_a, info_b):
    gap = calcular_gap_horizontal(info_a, info_b)
    sobreposicao_vertical = calcular_sobreposicao_vertical(info_a, info_b)

    if gap <= 0:
        return False

    if gap > GAP_MAXIMO_PIXELS:
        return False

    if sobreposicao_vertical < SOBREPOSICAO_VERTICAL_MINIMA:
        return False

    return True


def classificar_componentes(componentes):
    infos = [calcular_info_componente(c) for c in componentes]

    status = ["VALID" for _ in componentes]

    for i in range(len(componentes)):
        for j in range(i + 1, len(componentes)):
            if existe_espaco_pequeno_no_meio(infos[i], infos[j]):
                status[i] = "INVALID"
                status[j] = "INVALID"

    return infos, status


def preparar_imagem_base(imagem_original, mascara):
    altura, largura = mascara.shape

    if imagem_original is None:
        return np.zeros((altura, largura, 3), dtype=np.uint8)

    if imagem_original.shape[:2] != mascara.shape:
        imagem_base = cv2.resize(
            imagem_original,
            (largura, altura),
            interpolation=cv2.INTER_AREA
        )
    else:
        imagem_base = imagem_original.copy()

    if len(imagem_base.shape) == 2:
        imagem_base = cv2.cvtColor(imagem_base, cv2.COLOR_GRAY2BGR)

    elif imagem_base.shape[2] == 4:
        imagem_base = cv2.cvtColor(imagem_base, cv2.COLOR_BGRA2BGR)

    return imagem_base


def gerar_resultados_visuais(imagem_original, mascara, componentes):
    altura, largura = mascara.shape

    infos, status_componentes = classificar_componentes(componentes)

    resultado_colorido = np.zeros((altura, largura, 3), dtype=np.uint8)
    resultado_sobreposto = preparar_imagem_base(imagem_original, mascara)

    for indice, componente in enumerate(componentes, start=1):
        info = infos[indice - 1]
        status = status_componentes[indice - 1]

        if status == "INVALID":
            cor = VERMELHO
        else:
            cor = VERDE

        for x, y in componente:
            resultado_colorido[y, x] = cor

        x_min = info["x_min"]
        x_max = info["x_max"]
        y_min = info["y_min"]
        y_max = info["y_max"]

        cv2.rectangle(
            resultado_sobreposto,
            (x_min, y_min),
            (x_max, y_max),
            cor,
            2
        )

        cv2.putText(
            resultado_sobreposto,
            status,
            (x_min, max(y_min - 8, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            cor,
            2
        )

    if imagem_original is None:
        resultado_final = resultado_colorido.copy()
    else:
        resultado_final = cv2.addWeighted(
            resultado_sobreposto,
            0.70,
            resultado_colorido,
            0.30,
            0
        )

    return resultado_colorido, resultado_final, infos, status_componentes


def salvar_h5_filtrado(caminho_saida, labels):
    with h5py.File(caminho_saida, "w") as arquivo_saida:
        arquivo_saida.create_dataset(
            "labels",
            data=(labels == ID_FILTRAR).astype(np.uint8),
            compression="gzip"
        )


def processar_arquivo_h5(caminho_h5):
    nome_arquivo = os.path.basename(caminho_h5)
    nome_base, _ = os.path.splitext(nome_arquivo)

    labels = carregar_labels_h5(caminho_h5)
    mascara = filtrar_id(labels, ID_FILTRAR)

    componentes = encontrar_componentes_conectados(mascara)

    imagem_original = carregar_imagem_associada(caminho_h5)

    resultado_colorido, resultado_final, infos, status = gerar_resultados_visuais(
        imagem_original,
        mascara,
        componentes
    )

    pasta_saida = os.path.join(PASTA_SAIDA, nome_base)
    os.makedirs(pasta_saida, exist_ok=True)

    caminho_mascara = os.path.join(pasta_saida, f"01_mascara_id_{ID_FILTRAR}.png")
    caminho_resultado_colorido = os.path.join(pasta_saida, "02_componentes_valid_invalid.png")
    caminho_resultado_final = os.path.join(pasta_saida, "03_resultado_sobreposto.png")
    caminho_h5_filtrado = os.path.join(pasta_saida, f"{nome_base}_id_{ID_FILTRAR}.h5")

    cv2.imwrite(caminho_mascara, mascara)
    cv2.imwrite(caminho_resultado_colorido, resultado_colorido)
    cv2.imwrite(caminho_resultado_final, resultado_final)

    salvar_h5_filtrado(caminho_h5_filtrado, labels)

    print(f"\nArquivo processado: {nome_arquivo}")
    print(f"Componentes encontrados para id={ID_FILTRAR}: {len(componentes)}")

    for i, info in enumerate(infos):
        print(
            f"C{i + 1} | "
            f"{status[i]} | "
            f"area={info['area']} | "
            f"centro=({info['centro_x']:.2f}, {info['centro_y']:.2f})"
        )

    print(f"Resultados salvos em: {pasta_saida}")


def main():
    if not os.path.exists(PASTA_ENTRADA):
        print(f"Erro: a pasta '{PASTA_ENTRADA}' não existe.")
        return

    os.makedirs(PASTA_SAIDA, exist_ok=True)

    arquivos_h5 = carregar_arquivos_h5_da_pasta(PASTA_ENTRADA)

    if len(arquivos_h5) == 0:
        print(f"Nenhum arquivo HDF5 encontrado na pasta '{PASTA_ENTRADA}'.")
        return

    for caminho_h5 in arquivos_h5:
        processar_arquivo_h5(caminho_h5)

    print("\nProcessamento finalizado.")
    print(f"Resultados salvos na pasta: {PASTA_SAIDA}")


if __name__ == "__main__":
    main()