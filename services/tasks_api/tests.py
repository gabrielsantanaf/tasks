import os
import uuid

import jwt
import pytest
from fastapi import status
from starlette.testclient import TestClient

from main import app, get_task_store
from models import Task, TaskStatus

# Configurar variáveis de ambiente para testes
os.environ["AWS_DEFAULT_REGION"] = "eu-west-1"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"


class MockTaskStore:
    """TaskStore mockado para testes"""

    def __init__(self):
        self.tasks = {}

    def add(self, task: Task):
        """Adiciona uma tarefa"""
        key = f"{task.owner}#{task.id}"
        self.tasks[key] = task

    def get_by_id(self, task_id: uuid.UUID, owner: str) -> Task:
        """Recupera tarefa por ID"""
        key = f"{owner}#{task_id}"
        return self.tasks.get(key)

    def list_open(self, owner: str):
        """Lista tarefas abertas"""
        return [
            task
            for task in self.tasks.values()
            if task.owner == owner and task.status == TaskStatus.OPEN
        ]

    def list_closed(self, owner: str):
        """Lista tarefas fechadas"""
        return [
            task
            for task in self.tasks.values()
            if task.owner == owner and task.status == TaskStatus.CLOSED
        ]

    def update(self, task: Task):
        """Atualiza uma tarefa"""
        key = f"{task.owner}#{task.id}"
        self.tasks[key] = task


@pytest.fixture
def mock_task_store():
    """Cria um TaskStore mockado"""
    return MockTaskStore()


@pytest.fixture
def client(mock_task_store):
    """Cliente de teste com TaskStore mockado"""
    app.dependency_overrides[get_task_store] = lambda: mock_task_store
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def user_email():
    return "bob@builder.com"


@pytest.fixture
def id_token(user_email):
    return jwt.encode({"cognito:username": user_email}, "secret")


def test_health_check():
    """
    GIVEN
    WHEN health check endpoint is called with GET method
    THEN response with status 200 and body OK is returned
    """
    client = TestClient(app)
    response = client.get("/api/health-check/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"message": "OK"}


def test_added_task_retrieved_by_id():
    """Teste do repositório - adicionar e recuperar tarefa por ID"""
    task_store = MockTaskStore()
    task = Task.create(uuid.uuid4(), "Clean your office", "john@doe.com")

    task_store.add(task)

    assert task_store.get_by_id(task_id=task.id, owner=task.owner) == task


def test_open_tasks_listed():
    """Teste do repositório - listar apenas tarefas abertas"""
    task_store = MockTaskStore()
    open_task = Task.create(uuid.uuid4(), "Clean your office", "john@doe.com")
    closed_task = Task(
        uuid.uuid4(), "Clean your office", TaskStatus.CLOSED, "john@doe.com"
    )

    task_store.add(open_task)
    task_store.add(closed_task)

    assert task_store.list_open(owner=open_task.owner) == [open_task]


def test_closed_tasks_listed():
    """Teste do repositório - listar apenas tarefas fechadas"""
    task_store = MockTaskStore()
    open_task = Task.create(uuid.uuid4(), "Clean your office", "john@doe.com")
    closed_task = Task(
        uuid.uuid4(), "Clean your office", TaskStatus.CLOSED, "john@doe.com"
    )

    task_store.add(open_task)
    task_store.add(closed_task)

    assert task_store.list_closed(owner=open_task.owner) == [closed_task]


def test_create_task(client, user_email, id_token):
    """Teste da API - criar nova tarefa"""
    title = "Clean your desk"
    response = client.post(
        "/api/create-task", json={"title": title}, headers={"Authorization": id_token}
    )
    body = response.json()

    assert response.status_code == status.HTTP_201_CREATED
    assert body["id"]
    assert body["title"] == title
    assert body["status"] == "OPEN"
    assert body["owner"] == user_email


def test_list_open_tasks(client, user_email, id_token):
    """Teste da API - listar tarefas abertas"""
    title = "Kiss your wife"
    client.post(
        "/api/create-task", json={"title": title}, headers={"Authorization": id_token}
    )

    response = client.get("/api/open-tasks", headers={"Authorization": id_token})
    body = response.json()

    assert response.status_code == status.HTTP_200_OK
    assert body["results"][0]["id"]
    assert body["results"][0]["title"] == title
    assert body["results"][0]["owner"] == user_email
    assert body["results"][0]["status"] == "OPEN"


def test_close_task(client, user_email, id_token):
    """Teste da API - fechar uma tarefa"""
    title = "Read a book"
    response = client.post(
        "/api/create-task", json={"title": title}, headers={"Authorization": id_token}
    )

    response = client.post(
        "/api/close-task",
        json={"id": response.json()["id"]},
        headers={"Authorization": id_token},
    )
    body = response.json()

    assert response.status_code == status.HTTP_200_OK
    assert body["id"]
    assert body["title"] == title
    assert body["owner"] == user_email
    assert body["status"] == "CLOSED"


def test_list_closed_tasks(client, user_email, id_token):
    """Teste da API - listar tarefas fechadas"""
    title = "Ride big waves"
    response = client.post(
        "/api/create-task", json={"title": title}, headers={"Authorization": id_token}
    )
    client.post(
        "/api/close-task",
        json={"id": response.json()["id"]},
        headers={"Authorization": id_token},
    )

    response = client.get("/api/closed-tasks", headers={"Authorization": id_token})
    body = response.json()

    assert response.status_code == status.HTTP_200_OK
    assert body["results"][0]["id"]
    assert body["results"][0]["title"] == title
    assert body["results"][0]["owner"] == user_email
    assert body["results"][0]["status"] == "CLOSED"
