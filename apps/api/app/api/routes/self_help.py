"""«Решить самому»: an employee looks up an error code or a problem and gets the steps they can do
alone, plus the company document that answers — without opening a request."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from helpflow_ai.schemas import SelfHelp
from pydantic import BaseModel

from app.api.dependencies.auth import require_employee
from app.api.routes.conversations import DialogueDependency
from app.models.auth import User

router = APIRouter(prefix="/api/self-help", tags=["self-help"])

EmployeeDependency = Annotated[User, Depends(require_employee)]

# Codes people meet most often; shown as one-tap examples on the page.
POPULAR_CODES = ("809", "691", "0x800CCC0E", "0x00000709", "1603", "DNS_PROBE_FINISHED_NXDOMAIN", "0xCAA20002", "502")
POPULAR_TOPICS = (
    ("Не подключается VPN", "не подключается vpn"),
    ("Не печатает принтер", "принтер не печатает"),
    ("Не приходят письма", "не приходят письма в outlook"),
    ("Нет интернета или Wi-Fi", "нет интернета по wi-fi"),
    ("Не слышно в звонке", "меня не слышно в zoom"),
    ("Компьютер тормозит", "компьютер медленно работает"),
    ("Забыл пароль", "забыл пароль от учётной записи"),
    ("Не запускается программа", "программа не запускается"),
)


class PopularCode(BaseModel):
    code: str
    title: str


class PopularTopic(BaseModel):
    title: str
    query: str


class Popular(BaseModel):
    codes: list[PopularCode]
    topics: list[PopularTopic]


@router.get("", response_model=SelfHelp)
def search(
    service: DialogueDependency,
    _user: EmployeeDependency,
    q: Annotated[str, Query(max_length=300)] = "",
) -> SelfHelp:
    # The dialogue service loads the company's documents into the engine, so they count too.
    return service.engine.self_help(q)


@router.get("/popular", response_model=Popular)
def popular(service: DialogueDependency, _user: EmployeeDependency) -> Popular:
    kb = service.engine.kb
    codes = [PopularCode(code=code, title=entry.title)
             for code in POPULAR_CODES if (entry := kb.error_code(code)) is not None]
    return Popular(codes=codes, topics=[PopularTopic(title=t, query=q) for t, q in POPULAR_TOPICS])
