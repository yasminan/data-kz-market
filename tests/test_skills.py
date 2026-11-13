import pytest

from transform.skills import find_skills, vacancy_segment


def names(text):
    return {n for n, _ in find_skills(text)}


@pytest.mark.parametrize("text,expected,unexpected", [
    ("Опыт с SQL, PostgreSQL и ClickHouse", {"SQL", "PostgreSQL", "ClickHouse"}, set()),
    ("знание postgresql", {"PostgreSQL"}, {"SQL"}),
    ("Python / R для анализа", {"Python", "R"}, set()),
    ("Отдел R&D ищет специалиста", set(), {"R"}),
    ("Стек: Go, PostgreSQL, Kafka", {"Go", "PostgreSQL", "Kafka"}, set()),
    ("Let's go to the next level", set(), {"Go"}),
    ("Golang разработчик", {"Go"}, set()),
    ("уверенный Excel (сводные таблицы)", {"Excel"}, set()),
    ("excellent communication skills", set(), {"Excel"}),
    ("Power BI (DAX, Power Query)", {"Power BI"}, set()),
    ("JavaScript and TypeScript", {"JavaScript", "TypeScript"}, {"Java"}),
    ("Java 17, Spring", {"Java"}, {"JavaScript"}),
    ("знание казахского и английского языков", {"Kazakh", "English"}, set()),
    ("ағылшын тілін білу", {"English"}, set()),
    ("Опыт A/B тестирования и статистики", {"A/B testing", "Statistics"}, set()),
    ("BPMN, UML, Jira, Confluence", {"BPMN", "UML", "Jira", "Confluence"}, set()),
    ("XGBoost, CatBoost, scikit-learn", {"Gradient boosting", "scikit-learn"}, set()),
    ("send your CV to hr@company.kz", set(), {"Computer vision"}),
    ("1С:Бухгалтерия", {"1C"}, set()),
    ("Отклик: https://halykbank.kz/index.php/about/career/vacancies", set(), {"PHP"}),
    ("Резюме на ostyakov.pavel@huawei.com с префиксом в теме", set(), {"Machine learning"}),
    ("Опыт с Node.js и Vue", {"JavaScript"}, set()),
])
def test_find_skills(text, expected, unexpected):
    found = names(text)
    assert expected <= found
    assert not (unexpected & found)


def test_vacancy_segment_splits_digest():
    post = ("Вакансии:\nData Analyst\nТребования: SQL, Power BI\n\n"
            "Backend Developer\nТребования: Java, Kafka")
    titles = ["Data Analyst", "Backend Developer"]
    first = vacancy_segment(post, titles, 0)
    second = vacancy_segment(post, titles, 1)
    assert names(first) == {"SQL", "Power BI"}
    assert names(second) == {"Java", "Kafka"}
