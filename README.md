# Field Identifier Service

---

## Descrição geral

Este projeto implementa um serviço para identificar campos agrícolas ou regiões de interesse em imagens de satélite, utilizando tiles de mapas online. O processamento envolve o download de imagens por meio de coordenadas geográficas e a aplicação de técnicas de visão computacional para detectar contornos e gerar polígonos no formato WKT.

---

## Pré-requisitos

Antes de usar o projeto, você precisa garantir que as seguintes dependências estão instaladas no seu ambiente:

- **Python 3.8** ou superior
- **Bibliotecas necessárias:**
  ```bash
  pip install numpy opencv-python geopandas shapely requests pillow matplotlib
  
---

## Funcionamento geral

A classe "FieldIdentifierService" guarda todas as funções necessárias pro funcionamento do serviço, a função "identify_fields" é a principal, segue o funcionamento dela:

Recebe como parâmetros a latitude e a longitude do tile central e o tipo da identificação dos talhões, variando de 0 a 3. O tipo da identificação diz respeito a diferentes parâmetros 
que influenciam na identificação dos talhões, para o tipo 0 e 1 a identificação será feita no zoom 15 e para os tipos 2 e 3 no zoom 16, o que diferencia os tipos 0 do 1 e 2 do 3 são os parâmetros que posteriormente serão passados na função "processa_imagem".

**1** - Baixar os tiles necessários e junta-los em uma só imagem: o primeiro passo do "identify_fields" está na função "juntar_tiles_regiao", ela recebe como parâmetros a latitude e longitude do tile central, o zoom dos quais os tiles vão ser baixados e o "tile_gap_x" e "tile_gap_y", que basicamente representam quantos tiles a mais serão baixados na horizontal e na vertical, se o tile_gap_x for 3 e o y for 2, partindo do tile central serão baixados 2 tiles a mais pra cima e pra baixo e mais 3 pros lados, ou seja, a região será um retângulo 5x7. A função "juntar_tiles_região" primeiramente transforma as coordenadas de latitude e longitude para cartesianas, x e y, pois os tiles são distintos por coordenadas cartesianas. Em seguida, paralelamente usando threads, baixa todos os tiles com a função "_download_single_tile", que utilizando a API do google maps, baixa as imagens e concatena, as imagens estão sendo baixadas de uma maneira duvidosa, a gente não paga de fato a API do google maps, então algumas vezes atinge o limite de requisição e precisa reiniciar o código. Em seguida converte novamente as coordenadas cartesianas dos tiles maximos e minimos em latitude e longitude para calcular a bounding box, assim a função retorna a imagem com todos os tiles, os bounds e o número de tiles que foi baixado. A classe "FieldIdentifierService" tem em seu construtor um cache que guarda os tiles que ja foram baixados, pra caso o usuário volte para uma mesma região, não precise baixar os tiles novamente e, assim, otimizar tempo. 

**2** - Processar a imagem conforme o tipo: a função "processar_imagem" 1 e 2 são o núcleo do código, as funções responsáveis por de fato processar imagem e identificar os talhões. Essa é a parte complexa de se fazer funcionar consistentemente. A maneira como eu estou fazendo é aplicando uma série de processos na imagem para que seja possível identificar as variações de cores. A diferença do "processar_imagem" 1 e 2 é a de que o 2 contém mais um passo de processamento. Vou escrever um tópico exclusivo para essa função mais a frente, mas em resumo ela recebe alguns parâmetros de ajuste na identificação, como o tamanho minimo para um talhão ser considerado, e retorna o contorno dos talhões e a hierarquia, que vai definir se um contorno é um talhão ou um buraco.

**3** - Transformar os contornos em polígonos e salvar no formato wkts: Baseado no bounding box, na largura da imagem e nos pontos dos contornos se converte os contornos em polígonos com coordenadas latitude e longitude, cria uma lista chamada "poligonos", para cada elemento de "poligonos" cria um dicionário com o polígono transformato em wkt e um id, que é salvo em uma lista chamada "wkts" que é, finalmente, retornada e finalizado o processo.

---

## Função "processar_imagem"

A função "processar_imagem" recebe como parâmetro:

- imagem (a imagem que vai ser processada)

- blur (um número natural ímpar que dita o quanto a imagem vai ficar borrada em determinado nível do processo)

- area (dita a área mínima, em pixels, para um talhão ser considerado)

- sol (dita a solidez mínima de um talhão para ser considerado, vai ser explicado melhor)

Ela segue uma série de passos de processamentos utilizando a bilioteca cv2 na imagem para tentar identificar os talhões, são eles, em relação ao "processar_imagem_1":

**1** - *hsv = cv2.cvtColor(imagem, cv2.COLOR_BGR2HSV)*
        Converte a imagem em HSV (Hue Saturation Value), o padrão em detecção de imagens é converter para cinza, entretanto HSV pareceu dar mais resultado.

**2** - *hsv_blur = cv2.GaussianBlur(hsv, (blur, blur), 0)*
        Aplica um desfoque na imagem. É importante pois deixa as regiões mais uniformes, por exemplo uma plantação de trigo poderia ter cada linha de plantação identificada como um talhão sem esse passo, identificaria muito mais detalhes do que o desejado, além de ficar muito inconsistente. Quanto maior o zoom dos talhões baixados, maior a qualidade e mais detalhada a imagem, assim é necessário mais blur. 

**3** - *edges = cv2.Canny(hsv_blur, 50, 150)*
        Distingue as cores e traça as bordas dos talhões. Retorna uma imagem preta e branca, com os limites sendo bordas brancas.

**4** - *kernel = np.ones((4,4), np.uint8)*
        *edges = cv2.dilate(edges, kernel, iterations=1)*
        *edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)*
        Dilata e fecha as bordas. Basicamente, distingue os talhões grudados, depois da identificação das bordas, muitos dos talhões ficam "grudados", dois talhões quadrados por exemplo, que tem um vertice em comum, acabam
        sendo salvos como um só, esse passo serve pra distinguir esses talhões. Quanto maior o valor no np.ones((4,4), np.uint8), mais dilatadas as bordas, o problema é que com valores muito altos os talhões ficam "encolhidos",
        3 parece um valor decente.

**5** - *_, edges_inv = cv2.threshold(edges, 127, 255, cv2.THRESH_BINARY_INV)*
        *cleaned = self.remove_white(edges_inv, area, area)*
        Nesse instante, os talhões estão identificados como preto e as partes que não nos interessam de branco, *_, edges_inv = cv2.threshold(edges, 127, 255, cv2.THRESH_BINARY_INV)*, simplesmente inverte as cores.
        A função "remove_white" verifica a área de cada região branca, se for menor que a área mínima "pinta" a região de preto, é um passo importante pois muito lixo é reconhecido, como árvores ou prédios.

**6** - *cleaned = self.solidez(cleaned, sol)*
        A função "solidez" basicamente calcula a área da região em questão e a área dela caso fosse um polígono convexo, se a proporção da primeira pela segunda for menor que a solidez do parâmetro ele apaga o talhão.
        Em outras palavras, se o talhão for muito inconsistente, caótico, a função o apaga, uma solidez de 0.3 parece razoável.

**7** - A função "findContours" procura os limites das regiões brancas e traça contornos, se um contorno for desenhado dentro de outro ele será considerado um buraco, o que define isso é a hierarquia de um contorno.
        O epsilon = 0.001 * cv2.arcLength(cnt, True) é responsável por simplificar os contornos, quanto maior o termo multiplicando mais simplificado, assim é retornada a lista approx_contours e as hierarquias.

O processar_imagem_2 é um caso específico em que eu coloquei um passo de processamento a mais, eu primeiro faço a identificação com um blur de 11, o que seleciona os talhões de uma maneira bem geral, depois faço novamente
o processamento com um blur de 5, capturando mais detalhadamente.

---

# Considerações finais

A velocidade de processamento do código está suficiente, o maior problema atual é a precisão com que os talhões estão sendo gerados, muitos ficam inutilizáveis. Idealmente, os parâmetros da função de processamento deveriam
ser definidos através de machine learning, eu fui testando na mão, adicionar mais passos no processamento e achar os melhores parâmetros podem ser solução. Achar outra API de imagem pode ajudar também.

