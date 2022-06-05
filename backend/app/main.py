from lib2to3.pgen2 import token
from typing import List
from unicodedata import name
from pydantic import BaseModel
from fastapi import FastAPI, File, UploadFile, Form



from util.read_input import preprocess
from score_logic import compute_final_score


import torch
import json
import numpy as np
import pandas as pd
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from sentence_transformers import SentenceTransformer
from keyword_checker import checker
from numpy import dot
from numpy.linalg import norm


model = None
device = None
tokenizer = None

sbert_model = None
LOAD_FROM = 'kimcando/sbert-kornli-knoSTS-trained'


def sentences_predict(model, tokenizer, sent_A, sent_B):
    model.eval()
    tokenized_sent = tokenizer(
        sent_A,
        sent_B,
        padding=True,
        return_tensors="pt",
        truncation=True,
        add_special_tokens=True,
        max_length=64,
    )
    tokenized_sent.to("cuda:0")
    # print(tokenized_sent)
    with torch.no_grad():  # 그라디엔트 계산 비활성화
        outputs = model(
            input_ids=tokenized_sent["input_ids"],
            attention_mask=tokenized_sent["attention_mask"],
            token_type_ids=tokenized_sent["token_type_ids"],
        )
    logits = outputs[0]
    logits = logits.detach().cpu().numpy()
    result = np.argmax(logits)

    if result == 0:
        result = "non_similar"
    elif result == 1:
        result = "similar"
    return result, logits


def load_refine_json_data(data):
    student_id = []
    answers = []
    for student_pair in data["answers"]:
        student_id.append(student_pair[0])
        answers.append(student_pair[1])

    # answers = pd.read_csv("./example.csv")["answer"].to_list()  # example
    # tmp. 실제 json 데이터 찾아서 읽어야 함
    gold_answer = [data["gold_answer"]] * len(answers)
    return student_id, answers, gold_answer


def make_problem_df(problem, problem_idx, sim_score, student_id, answers):
    new_data = {}
    new_data["problem_idx"] = problem_idx
    new_data["question"] = problem["question"]
    new_data["gold_answer"] = problem["gold_answer"]
    new_data["keywords"] = problem["keywords"]

    result = []
    result_dict = {}
    result_len = len(student_id)
    for i in range(result_len):
        result_dict = {}
        check_score, match_info = checker(answers[i], new_data["keywords"])
        result_dict["student_id"] = student_id[i]
        result_dict["answer"] = answers[i]
        result_dict["sim_score"] = round(sim_score[i].astype(np.float64), 4)
        result_dict["keyword_score"] = check_score
        result_dict["total_score"] = round(sim_score[i] + check_score, 4)
        result_dict["final_score"] = compute_final_score(check_score, round(sim_score[i].astype(np.float64),4))
        result_dict["match_info"] = match_info
        result.append(result_dict)

    new_data["result"] = result
    return new_data



def inference_model(data):
    # device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    # tokenizer = AutoTokenizer.from_pretrained("xuio/sts-12ep")
    # model = AutoModelForSequenceClassification.from_pretrained(
    #     "kimcando/para_test_4800"
    # )
    # model.cuda()
    #subject = data["subject"]  # 과목

    output_dict = {}
    #output_dict["subject"] = data["subject"]
    new_problem = []

    for i, problem in enumerate(data):
        # for i, problem in range(data["problem"][0]):
        problem_idx = i
        student_id, answers, gold_answer = load_refine_json_data(problem)
        result, logits = sentences_predict(model, tokenizer, answers, gold_answer)
        softmax = torch.nn.Softmax(dim=1)
        prob = softmax(torch.tensor(logits))
        ans = prob.argmax(dim=1)
        sim_score = prob.detach().cpu().numpy()[:, 0]

        individual_df = make_problem_df(problem, i, sim_score, student_id, answers)
        new_problem.append(individual_df)

          # 예시가 하나만 있기 때문에 들어가있는 break. 실제 json을 넘겨줄 시 지워야 한다
    output_dict["problem"] = new_problem
    #output_json = json.dumps(output_dict)
    # with open("./result.json", "w") as f:  # result 눈으로 확인하는 용도
    #     json.dump(output_dict, f, ensure_ascii=False, indent=4)
    return output_dict


##sbert


def get_similarity(ans, right_ans, use="cosine"):
    # Cosine Similarity
    if use == "cosine":
        return dot(ans, right_ans) / (norm(ans) * norm(right_ans))

    # Euclidean
    if use == "euclidean":
        if norm(ans - right_ans) == norm(ans - right_ans):
            return norm(ans - right_ans)
        else:
            return -1

    # Pearson
    if use == "pearson":
        return dot((ans - np.mean(ans)), (right_ans - np.mean(right_ans))) / (
                    (norm(ans - np.mean(ans))) * (norm(right_ans - np.mean(right_ans))))


def sentences_sbert_predict(emb_a, emb_b):
    results = []
    for idx, (a, b) in enumerate(zip(emb_a, emb_b)):
        sim_score = get_similarity(a, b, use="cosine")
        results.append(round(sim_score,2))
    return results


def inference_sbert_model(data):

    output_dict = {}


    new_problem = []
    # gold_answer = ['제과점끼리 경쟁 심화가 커질 수 있다.', '맛이 더 좋아질 수는 있따']
    # answers = ['제과점끼리 경쟁이 작아질 수 있다.', '더 좋은 맛을 누릴 수 있다'] # 경쟁이 커질 수 있다로 하면 낮게나옴
    for problem_idx, problem in enumerate(data):
    # for i, problem in enumerate([1,3]):
        # for i, problem in range(data["problem"][0]):
        student_id, answers, gold_answer = load_refine_json_data(problem)

        right_ans_emb = sbert_model.encode(gold_answer)
        stu_ans_emb = sbert_model.encode(answers)
        sim_score = sentences_sbert_predict(right_ans_emb, stu_ans_emb)
        individual_df = make_problem_df(problem, problem_idx, sim_score, student_id, answers)
        new_problem.append(individual_df)

        
    output_dict["problem"] = new_problem
    # output_json = json.dumps(output_dict)
    # with open("./result.json", "w") as f:  # result 눈으로 확인하는 용도
    #     json.dump(output_dict, f, ensure_ascii=False, indent=4)
    return output_dict




app = FastAPI()

class Problem(BaseModel):
    question: str
    gold_answer: str
    keywords: list
    answers : list

class ProblemList(BaseModel):
    problem: List[Problem]


# before startup, load model
@app.on_event("startup")
async def modelUp():

    print("model uploading")

    global device, tokenizer, model, sbert_model
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained("xuio/sts-12ep")
    model = AutoModelForSequenceClassification.from_pretrained(
        "kimcando/para_test_4800"
    )
    model.cuda()

    sbert_model = SentenceTransformer(LOAD_FROM)
    sbert_model.cuda()

    print("done")

#from here API
@app.get("/api/")
def read_root():
    return "hello gompada"


@app.post("/api/input")
def read_item(data : ProblemList):

    data_dict = []
    for x in data.problem:
        data_dict.append(dict(x))
    #print(data_dict)
    #output = inference_model(data_dict)
    output = inference_sbert_model(data_dict)
    #print(output)

    return output



# main 함수 만들고 배포시에는 백그라운드로 돌려놓기
#initial
# uvicorn main:app --host=0.0.0.0 --port=8000 --reload
'''
if __name__ == "__main__":
    #csv db를 sqlte로 미
    print("server start")
    uvicorn.run(app, host="127.0.0.1", port=8000)
    #for producton
    #uvicorn main:app --host=0.0.0.0 --port=8000 &

    #for test
    #uvicorn main:app --host=0.0.0.0 --port=8000 --reload
'''