"""Acceptance tests for the five request types the jury checks.

Principle under test: the user never answers a question that is not needed to
pick the next step, and never repeats what the first message already said.
"""

from __future__ import annotations

import pytest

from helpflow_ai import DecisionAction, StepOutcome

CASE_EXAMPLE = ("У меня опять всё сломалось. Вчера всё работало, сегодня не могу зайти в рабочую систему. "
                "Через телефон открывается, с ноутбука нет. Мне через 20 минут на встречу")


def first_question_facts(sim) -> list[str]:
    facts = []
    while sim.decision.action == DecisionAction.ASK:
        facts.append(sim.decision.question.fact)
        sim.answer("не знаю")
    return facts


# --- unsolvable by the user: new access ------------------------------------

ACCESS = "Нужен доступ к папке бухгалтерии на общем диске"


def test_access_request_extracts_named_resource(engine):
    analysis = engine.analyze(ACCESS)
    assert analysis.recommended_playbook == "access_rights"
    assert "бухгалтерии" in analysis.known_facts["resource"]
    assert "resource" not in analysis.missing_facts


def test_new_access_goes_to_admins_without_questions(simulate, engine):
    sim = simulate(ACCESS)
    assert sim.decision.action == DecisionAction.ESCALATE
    assert sim.decision.escalation_team == "Администраторы доступа"
    assert "папке бухгалтерии" in sim.decision.message

    card = engine.build_escalation_card(sim.ctx, sim.decision.reason)
    assert "бухгалтерии" in card.known_facts["resource"]
    assert card.questions_and_answers == []


@pytest.mark.parametrize("message, resource", [
    ("Дайте доступ в 1С, я новый сотрудник", "1С"),
    ("пожалуйста откройте доступ к шаре Marketing, горит отчёт!!", "шаре Marketing"),
    ("нужен доступ в джиру к проекту SALES", "джиру к проекту SALES"),
])
def test_access_variations_do_not_ask_for_named_resource(simulate, message, resource):
    sim = simulate(message)
    assert sim.analysis.recommended_playbook == "access_rights"
    assert resource.lower() in sim.ctx.known_facts["resource"].lower()
    assert "resource" not in first_question_facts(sim)


def test_lost_access_still_troubleshoots(simulate):
    sim = simulate("Пропал доступ к папке отдела на общем диске, пишет доступ запрещён")
    assert sim.analysis.recommended_playbook == "access_rights"
    assert "resource" not in first_question_facts(sim)
    assert sim.decision.action == DecisionAction.STEP


# --- urgent: the fastest workaround first, questions depend on the symptom --

TEAMS_URGENT = "Через 5 минут звонок с клиентом, не запускается Teams, горит!"


def test_urgent_app_start_failure_is_understood(engine):
    analysis = engine.analyze(TEAMS_URGENT)
    assert analysis.recommended_playbook == "video_calls"
    assert analysis.urgency.value == "high"
    assert "приложение не запускается" in analysis.symptoms
    assert analysis.known_facts["call_app"] == "teams"
    assert analysis.next_question is None, "nothing to ask: the app and the symptom are known"


def test_urgent_call_starts_with_workaround_not_questions(simulate):
    sim = simulate(TEAMS_URGENT)
    assert sim.decision.action == DecisionAction.STEP
    assert sim.decision.step.workaround is True
    assert "браузер" in sim.decision.message and "телефон" in sim.decision.message


def test_app_start_failure_never_asks_about_headset(simulate):
    sim = simulate(TEAMS_URGENT)
    seen_steps = []
    while sim.decision.action in (DecisionAction.STEP, DecisionAction.ASK):
        assert sim.decision.action == DecisionAction.STEP, "no questions needed here"
        seen_steps.append(sim.decision.step.id)
        sim.step_result(StepOutcome.NOT_HELPED)
    assert "reconnect_headset" not in seen_steps
    assert "check_mute_and_device" not in seen_steps
    assert "restart_call_app" in seen_steps
    assert sim.decision.action == DecisionAction.ESCALATE


def test_helpful_workaround_does_not_close_the_real_problem(simulate):
    sim = simulate(TEAMS_URGENT)
    sim.step_result(StepOutcome.HELPED)
    assert sim.decision.action == DecisionAction.STEP
    assert sim.decision.step.id == "restart_call_app"
    assert "позже" in sim.decision.message or "минут" in sim.decision.message


@pytest.mark.parametrize("message", [
    "СРОЧНО через 10 мин созвон, зум не запускаеться!!!",
    "тимс не открывается а у меня звонок через пару минут",
    "Помогите быстрее, презентация через 3 минуты, Zoom вылетает при запуске",
])
def test_urgent_call_variations_start_with_workaround(simulate, message):
    sim = simulate(message)
    assert sim.analysis.urgency.value in ("high", "critical")
    assert sim.decision.action == DecisionAction.STEP and sim.decision.step.workaround
    sim.step_result(StepOutcome.NOT_HELPED)
    assert "headset" not in first_question_facts(sim)


def test_urgent_sound_problem_offers_phone_first(simulate):
    sim = simulate("Меня не слышат в Zoom, через 5 минут презентация у клиента!")
    assert sim.decision.action == DecisionAction.STEP and sim.decision.step.workaround


def test_calm_sound_problem_asks_about_headset(simulate):
    sim = simulate("Меня не слышат в Teams")
    assert sim.decision.action == DecisionAction.ASK
    assert sim.decision.question.fact == "headset"


def test_vague_call_problem_asks_what_exactly_is_wrong(simulate):
    sim = simulate("Проблемы с зумом, помогите")
    assert sim.decision.action == DecisionAction.ASK
    assert sim.decision.question.fact == "call_problem"
    sim.answer("меня не слышат собеседники")
    assert sim.decision.action == DecisionAction.ASK
    assert sim.decision.question.fact == "headset"


def test_urgent_lost_internet_offers_phone_hotspot_first(simulate):
    sim = simulate("срочно!! интернет пропал, а через 10 минут созвон с клиентом")
    assert sim.analysis.recommended_playbook == "network_wifi"
    assert sim.decision.action == DecisionAction.STEP and sim.decision.step.workaround
    assert "раздач" in sim.decision.message


def test_calm_lost_internet_keeps_regular_order(simulate):
    sim = simulate("Интернет пропал на ноутбуке")
    assert sim.decision.action == DecisionAction.ASK


# --- what we understood is used, meaningless questions are not asked --------

PRINTER = "Принтер не печатает, пишет замятие бумаги"


def test_printer_jam_is_understood(engine):
    analysis = engine.analyze(PRINTER)
    assert analysis.recommended_playbook == "printer"
    assert analysis.service == "Принтер"
    assert "замятие бумаги" in analysis.symptoms
    assert "замятие" in analysis.known_facts["error_text"]


def test_printer_jam_starts_with_clearing_the_jam(simulate):
    sim = simulate(PRINTER)
    assert sim.decision.action == DecisionAction.STEP
    assert sim.decision.step.id == "clear_paper_jam"


@pytest.mark.parametrize("message, first_step", [
    ("принтер зажевал бумагу((", "clear_paper_jam"),
    ("не печатает мфу на 3 этаже, ничего не пишет", "check_printer_ready"),
    ("Отправляю на печать документ, а принтер молчит и не печатает", "check_printer_ready"),
])
def test_printer_variations_skip_pointless_questions(simulate, message, first_step):
    sim = simulate(message)
    assert sim.analysis.recommended_playbook == "printer"
    assert sim.decision.action == DecisionAction.STEP
    assert sim.decision.step.id == first_step


def test_printer_without_details_asks_what_it_shows(simulate):
    sim = simulate("Принтер сломался")
    assert sim.decision.action == DecisionAction.ASK
    assert sim.decision.question.fact == "error_text"


def test_printer_jam_that_does_not_clear_goes_to_specialist(simulate, engine):
    sim = simulate(PRINTER)
    while sim.decision.action == DecisionAction.STEP:
        sim.step_result(StepOutcome.NOT_HELPED)
    assert sim.decision.action == DecisionAction.ESCALATE
    card = engine.build_escalation_card(sim.ctx, sim.decision.reason)
    assert card.service == "Принтер"
    assert "замятие" in card.known_facts["error_text"]
    assert len(card.performed_steps) >= 2


@pytest.mark.parametrize("message, subject", [
    ("Мышка перестала работать", "Мышь"),
    ("не включается монитор, горит оранжевая лампочка!!", "Монитор"),
    ("клава не печатает русские буквы", "Клавиатура"),
])
def test_named_device_without_playbook_is_handed_off_at_once(simulate, engine, message, subject):
    sim = simulate(message)
    assert sim.analysis.recommended_playbook == "unknown"
    assert sim.analysis.service == subject
    assert sim.decision.action == DecisionAction.ESCALATE, "no pointless 'which program?' question"
    assert "готового решения" in sim.decision.message.lower()
    card = engine.build_escalation_card(sim.ctx, sim.decision.reason)
    assert card.original_request == message
    assert card.service == subject
    assert subject in card.summary


@pytest.mark.parametrize("message", [
    "Ничего не работает, помогите пожалуйста",
    "всё тупит и глючит, сделайте что-нибудь!!!",
    "у меня какая-то беда с компом не пойму что",
])
def test_ambiguous_request_asks_what_is_broken_first(simulate, message):
    sim = simulate(message)
    assert sim.decision.action == DecisionAction.ASK
    # One question with the likely areas as buttons, not a questionnaire.
    assert sim.decision.question.fact == "problem_area"
    asked = first_question_facts(sim)
    assert len(asked) <= 3 and len(asked) == len(set(asked))


# --- several symptoms: all found, root cause first, the rest follows --------

MULTI = "Outlook не синхронизируется, а ещё в Zoom нет звука и интернет постоянно отваливается"


def issue_ids(issues) -> set[str]:
    return {issue.playbook_id for issue in issues}


def test_all_problems_are_recognized_and_network_goes_first(engine):
    analysis = engine.analyze(MULTI)
    assert analysis.recommended_playbook == "network_wifi", "unstable internet breaks the rest"
    assert issue_ids(analysis.additional_issues) == {"email_outlook", "video_calls"}
    assert "частые разрывы" in analysis.symptoms
    evidence = " ".join(issue.evidence for issue in analysis.additional_issues)
    assert "Outlook" in evidence and "Zoom" in evidence
    symptoms = {i.playbook_id: i.symptoms for i in analysis.additional_issues}
    assert symptoms["email_outlook"] == ["почта не синхронизируется"]
    assert symptoms["video_calls"] == ["не слышно собеседников"]


def test_user_is_told_the_rest_comes_next(simulate):
    sim = simulate(MULTI)
    message = sim.decision.message
    assert "Outlook" in message and "Zoom" in message and "следом" in message
    assert sim.decision.playbook_id == "network_wifi"


def test_problems_are_worked_through_one_by_one(simulate):
    sim = simulate(MULTI)
    while sim.decision.action == DecisionAction.ASK:
        sim.answer("в офисе" if sim.decision.question.fact == "location" else "да")
    assert sim.decision.action == DecisionAction.STEP
    assert sim.decision.playbook_id == "network_wifi"

    sim.step_result(StepOutcome.HELPED)  # internet is stable now
    assert sim.decision.action == DecisionAction.ASK
    assert "Outlook" in sim.decision.message
    check = sim.decision.question.fact

    sim.answer("нет, всё так же не синхронизируется")
    assert sim.ctx.known_facts[check] == "no"
    while sim.decision.action == DecisionAction.ASK:
        sim.answer("никакой ошибки нет")
    assert sim.decision.action == DecisionAction.STEP
    assert sim.decision.playbook_id == "email_outlook"
    assert sim.decision.step.id == "check_web_mail"

    # Mail in the browser is a way around, not a fix: Outlook itself is repaired next.
    sim.step_result(StepOutcome.HELPED)
    assert sim.decision.action == DecisionAction.STEP
    assert sim.decision.step.id == "restart_outlook"

    sim.step_result(StepOutcome.HELPED)
    assert sim.decision.action == DecisionAction.ASK
    assert "Zoom" in sim.decision.message
    sim.answer("да, звук появился")
    assert sim.decision.action == DecisionAction.VERIFY
    assert sim.verify("да, всё работает") is True


def test_escalation_card_lists_every_problem(simulate, engine):
    sim = simulate(MULTI)
    while sim.decision.action == DecisionAction.ASK:
        sim.answer("из дома")
    while sim.decision.action == DecisionAction.STEP:
        sim.step_result(StepOutcome.NOT_HELPED)
    assert sim.decision.action == DecisionAction.ESCALATE

    card = engine.build_escalation_card(sim.ctx, sim.decision.reason)
    assert card.original_request == MULTI
    assert issue_ids(card.issues) == {"network_wifi", "email_outlook", "video_calls"}
    statuses = {issue.playbook_id: issue.status for issue in card.issues}
    assert statuses == {"network_wifi": "in_progress", "email_outlook": "pending", "video_calls": "pending"}
    assert card.recommended_team == "Сетевые администраторы"
    assert "Outlook" in card.ai_summary and "Zoom" in card.ai_summary


@pytest.mark.parametrize("message, primary, others", [
    ("почта не открывается и впн отваливается постоянно", "vpn_connection", {"email_outlook"}),
    ("задолбало: зум лагает, и аутлук не отправляет письма!!!", "email_outlook", {"video_calls"}),
    ("Не работает почта и интернет", "network_wifi", {"email_outlook"}),
    ("Почта и интернет не работают с утра", "network_wifi", {"email_outlook"}),
])
def test_multi_problem_variations(engine, message, primary, others):
    analysis = engine.analyze(message)
    assert analysis.recommended_playbook == primary
    assert issue_ids(analysis.additional_issues) == others


@pytest.mark.parametrize("message", [
    CASE_EXAMPLE,
    "Outlook постоянно просит пароль и письма не отправляются, застряли в исходящих",
    "Не могу войти в CRM, VPN подключен, пишет «Сессия истекла»",
    "В офисе нет интернета на ноутбуке, вай-фай подключен но без доступа к интернету",
    "Меня не слышат в Zoom, через 5 минут презентация у клиента!",
    "срочно!! интернет пропал, а через 10 минут созвон с клиентом",
    TEAMS_URGENT, PRINTER, ACCESS,
    "Ошибка 502 в CRM",
    "CRM не работает, срочно. VPN подключен, ошибка 403",
    "Zoom не запускается, пишет «ошибка 1001»",
    "VPN подключен и CRM всё равно не открывается",
])
def test_single_problem_is_not_split(engine, message):
    assert engine.analyze(message).additional_issues == []


# --- the case example must keep working ------------------------------------

def test_case_example_is_unchanged(simulate):
    sim = simulate(CASE_EXAMPLE)
    assert sim.analysis.recommended_playbook == "crm_login_device_specific"
    assert sim.analysis.urgency.value == "high"
    assert "встреча через 20 минут" in sim.analysis.urgency_reason
    assert sim.decision.action == DecisionAction.ASK
    assert sim.decision.question.fact == "error_text"
    assert "несколько" not in sim.decision.message


# --- simple: start solving after at most one question -----------------------

@pytest.mark.parametrize("message, first_step", [
    ("Забыл пароль от учётки, не срочно", "self_service_reset"),
    ("не могу зайти в винду, пароль не подходит((", "check_keyboard_layout"),
    ("аааа учетку заблокировали, что делать", "check_keyboard_layout"),
])
def test_simple_requests_start_solving_quickly(simulate, message, first_step):
    sim = simulate(message)
    assert sim.analysis.recommended_playbook == "password_login"
    asked = first_question_facts(sim)
    assert len(asked) <= 1
    assert "error_text" not in asked, "the symptom is already clear from the text"
    assert sim.decision.action == DecisionAction.STEP
    assert sim.decision.step.id == first_step


@pytest.mark.parametrize("message", [
    "Забыл пароль от почты, не могу войти",
    "не помню пароль от компа",
])
def test_forgotten_password_goes_straight_to_reset(simulate, message):
    sim = simulate(message)
    assert first_question_facts(sim) == [], "whether the password changed recently does not matter once it is forgotten"
    assert sim.decision.action == DecisionAction.STEP
    assert sim.decision.step.id == "self_service_reset"


def test_locked_account_waits_instead_of_resetting(simulate):
    sim = simulate("аааа учетку заблокировали, что делать")
    first_question_facts(sim)
    sim.step_result(StepOutcome.NOT_HELPED)
    assert sim.decision.step.id == "wait_lockout"


# --- the general rule: never ask what is already known ----------------------

ALL_MESSAGES = [
    CASE_EXAMPLE, MULTI, TEAMS_URGENT, ACCESS, PRINTER,
    "Не могу войти в CRM, VPN подключен, пишет «Сессия истекла»",
    "Из дома не подключается VPN, пишет \"authentication failed\"",
    "Outlook постоянно просит пароль и письма не отправляются, застряли в исходящих",
    "Меня не слышат в Zoom, через 5 минут презентация у клиента!",
    "почта не открывается и впн отваливается постоянно",
    "Ничего не работает, помогите пожалуйста",
]


@pytest.mark.parametrize("message", ALL_MESSAGES)
def test_no_question_about_a_known_fact(simulate, message):
    sim = simulate(message)
    for _ in range(12):
        if sim.decision.action == DecisionAction.ASK:
            fact = sim.decision.question.fact
            assert fact not in sim.ctx.known_facts, (fact, sim.ctx.known_facts)
            assert sim.ctx.asked_facts.count(fact) == 1, "questions never repeat"
            sim.answer("не знаю")
        elif sim.decision.action == DecisionAction.STEP:
            sim.step_result(StepOutcome.NOT_HELPED)
        else:
            break
    assert sim.decision.action in (DecisionAction.ESCALATE, DecisionAction.STEP)


def test_summary_does_not_repeat_the_title_in_other_words(engine):
    analysis = engine.analyze("Не подключается VPN из дома, пишет ошибку подключения")
    assert analysis.summary.count("VPN") == 1, analysis.summary
