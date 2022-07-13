from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import CountVectorizer
from sentence_transformers import SentenceTransformer
from konlpy.tag import Hannanum
from bs4 import BeautifulSoup
import requests
import re
import numpy as np
import pandas as pd


def kyoboExtract(ISBN: int) -> dict:
    kyoboUrl = f"http://www.kyobobook.co.kr/product/detailViewKor.laf?ejkGb=KOR&mallGb=KOR&barcode={ISBN}"
    kyoboHtml = requests.get(kyoboUrl)
    kyoboSoup = BeautifulSoup(kyoboHtml.content, "html.parser")

    bookTitle: str = kyoboSoup.h1.strong.string.strip()

    contents = kyoboSoup.find_all(class_="box_detail_article")
    sortedItems = []
    for item in contents:
        if item.find(class_="content"):
            # 숨겨진 항목을 불러오는 조건식
            item = item.find_all(class_="content")[-1]

        result = re.sub("<.*?>|\\s", " ", str(item))
        sortedItems.append(result)

    doc = "".join(sortedItems)
    doc: str = (
        # re.sub("[_-]|\d[.]|\d|[▶★●]", "", doc)
        re.sub("\d[.]|\d|\W|[_]", " ", doc)
        .replace("닫기", "")
        .replace("머신 러닝", "머신러닝")
        .replace("인공 지능", "인공지능")
        .replace("사용", "")
    )

    return dict(ISBN=ISBN, bookTitle=bookTitle, doc=doc)


# print(kyoboExtract(9791162242964))


def bookInfoExtraction(ISBN: str, model) -> list:
    """
    반복적으로 모델을 불러와야하는 문제를 개선하기 위해 변수에 model을 넣었음.
    모델을 미리 불러와야 한다.
    리턴 값으로 keyword를 반환함.
    """
    HTML = kyoboExtract(ISBN)

    # 제목
    print(HTML.get("bookTitle"))

    # 문서 정보 추출
    doc = HTML.get("doc")
    hannanum = Hannanum()
    hanNouns = hannanum.nouns(doc)
    testType = hanNouns
    words = " ".join(testType)
    vect = CountVectorizer(ngram_range=(1, 2))
    count = vect.fit([words])
    candidate = count.get_feature_names_out()

    doc_embedding = model.encode([doc])
    candidate_embeddings = model.encode(candidate)
    result: list = mmr(
        doc_embedding, candidate_embeddings, candidate, top_n=50, diversity=0.2
    )

    items = []
    for item in result:
        items.extend(item.split(" "))

    #
    # bertInfo = pd.DataFrame(items).groupby(by=0).size().sort_values(ascending=False).index[:20]
    # keyWordInfo = pd.DataFrame(testType).groupby(by=0).size().sort_values(ascending=False).index[:20]

    # print(list(set(bertInfo.append(keyWordInfo))))

    bertInfo = pd.DataFrame(items)
    keyWordInfo = pd.DataFrame(testType)

    keyWords = (
        pd.concat([bertInfo, keyWordInfo], axis=0)
        .groupby(by=0)
        .size()
        .sort_values(ascending=False)
        .index.tolist()
    )

    keyWords = list(filter(lambda a: a if len(a) > 1 else None, keyWords))

    return keyWords[:20]


def mmr(doc_embedding, candidate_embeddings, words, top_n, diversity):

    # 문서와 각 키워드들 간의 유사도가 적혀있는 리스트
    word_doc_similarity = cosine_similarity(candidate_embeddings, doc_embedding)

    # 각 키워드들 간의 유사도
    word_similarity = cosine_similarity(candidate_embeddings)

    # 문서와 가장 높은 유사도를 가진 키워드의 인덱스를 추출.
    # 만약, 2번 문서가 가장 유사도가 높았다면
    # keywords_idx = [2]
    keywords_idx = [np.argmax(word_doc_similarity)]

    # 가장 높은 유사도를 가진 키워드의 인덱스를 제외한 문서의 인덱스들
    # 만약, 2번 문서가 가장 유사도가 높았다면
    # ==> candidates_idx = [0, 1, 3, 4, 5, 6, 7, 8, 9, 10 ... 중략 ...]
    candidates_idx = [i for i in range(len(words)) if i != keywords_idx[0]]

    # 최고의 키워드는 이미 추출했으므로 top_n-1번만큼 아래를 반복.
    # ex) top_n = 5라면, 아래의 loop는 4번 반복됨.
    for _ in range(top_n - 1):
        candidate_similarities = word_doc_similarity[candidates_idx, :]
        target_similarities = np.max(
            word_similarity[candidates_idx][:, keywords_idx], axis=1
        )

        # MMR을 계산
        mmr = (
            1 - diversity
        ) * candidate_similarities - diversity * target_similarities.reshape(-1, 1)
        mmr_idx = candidates_idx[np.argmax(mmr)]

        # keywords & candidates를 업데이트
        keywords_idx.append(mmr_idx)
        candidates_idx.remove(mmr_idx)

    return [words[idx] for idx in keywords_idx]