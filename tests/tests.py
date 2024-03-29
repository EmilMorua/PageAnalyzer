import os
from dotenv import load_dotenv
import pytest
import datetime
from bs4 import BeautifulSoup
from requests.exceptions import RequestException

dotenv_path = os.path.join(os.path.dirname(__file__), '.env.test')
load_dotenv(dotenv_path)

from page_analyzer.app import app as _app  # noqa
from page_analyzer.extensions import db as _db  # noqa
from page_analyzer.models import Url, UrlCheck  # noqa
from page_analyzer.forms import URLForm  # noqa
from page_analyzer.handlers.add_check import (  # noqa
    create_check,
    save_check,
    get_shortened_h1_content,
    get_shortened_title_content,
    get_shortened_description_content
)


# Test data for use in tests
h1 = "<html><h1>This is a long title that needs to be shortened</h1></html>"
title = ("<html><title>This is a very long page"
         " title that needs to be shortened</title></html>")
description = ("<html><meta name='description' content='This is a very "
               "long page description that needs to be shortened'></html>")
expected_value_h1 = "This is a long title that needs to be shortened"
expected_value_title = ("This is a very long page "
                        "title that needs to be shortened")
expected_value_description = ("This is a very long page "
                              "description that needs to be shortened")
no_h1_tag = "<html><title>Title</title></html>"
no_title_tag = "<html><h1>Title</h1></html>"
text = ("<html><h1>Title</h1><title>Page Title</title><meta "
        "name='description' content='Page description'></html>")
test_url_name = "http://example.com"
html_parser = "html.parser"


class MockResponse:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text


@pytest.fixture(scope='session')
def app():
    db_uri = os.environ['SQLALCHEMY_DATABASE_URI']
    _app.config['SQLALCHEMY_TEST_DATABASE_URI'] = db_uri
    _app.config['WTF_CSRF_ENABLED'] = False
    ctx = _app.app_context()
    ctx.push()
    yield _app
    ctx.pop()


@pytest.fixture(scope='function')
def db(app):
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_url_model(db):
    test_url = Url(name=test_url_name)
    db.session.add(test_url)
    db.session.commit()

    assert test_url.id is not None
    assert test_url.name == test_url_name


def test_url_check_model(db):
    test_url = Url(name=test_url_name)
    db.session.add(test_url)
    db.session.commit()

    new_check = UrlCheck(
        url_id=test_url.id,
        created_at=datetime.datetime.utcnow(),
        status_code=200,
        h1_content=expected_value_h1,
        title_content=expected_value_title,
        description_content=expected_value_description
    )
    db.session.add(new_check)
    db.session.commit()

    assert new_check.id is not None
    assert new_check.url_id == test_url.id
    assert new_check.created_at is not None
    assert new_check.status_code == 200
    assert new_check.h1_content == expected_value_h1
    assert new_check.title_content == expected_value_title
    assert new_check.description_content == expected_value_description


def test_url_check_relationship(db):
    test_url = Url(name=test_url_name)
    db.session.add(test_url)

    new_check = UrlCheck(
        status_code=200,
        h1_content="Test H1 Content",
        title_content="Test Title Content",
        description_content="Test Description Content",
        url=test_url
    )
    db.session.add(new_check)
    db.session.commit()

    assert new_check.url is not None
    assert new_check.url_id == test_url.id
    assert new_check.url == test_url
    assert test_url.checks[0] == new_check


def test_valid_url():
    form = URLForm(url=test_url_name)
    assert form.validate() is True


def test_invalid_url():
    form = URLForm(url="invalid-url")
    assert form.validate() is False


def test_empty_url():
    form = URLForm(url="")
    assert form.validate() is False


def test_submit_button_label():
    form = URLForm()
    assert form.submit.label.text == "Submit"


def test_index_handler(client):
    response = client.get('/')
    assert response.status_code == 200


def test_urls_handler(client, db):
    test_url = Url(name=test_url_name)
    db.session.add(test_url)
    db.session.commit()

    response = client.get('/urls')
    assert response.status_code == 200
    assert test_url_name.encode('utf-8') in response.data


def test_url_detail_handler(client, db):
    test_url = Url(name=test_url_name)
    db.session.add(test_url)
    db.session.commit()

    response = client.get('/urls/1')
    assert response.status_code == 200
    assert test_url_name.encode('utf-8') in response.data


def test_handle_url_post_invalid_url(client):
    response = client.post('/urls', data={'url': 'invalid-url'})
    assert response.status_code == 302
    assert "Некорректный URL" not in response.get_data(as_text=True)
    assert response.location.endswith("/")


def test_handle_url_post_empty_url(client):
    response = client.post('/urls', data={'url': ''}, follow_redirects=True)
    assert response.status_code == 200
    assert "URL обязателен" in response.get_data(as_text=True)


def test_add_check_handler(db):
    new_check = UrlCheck(
        url_id=1,
        created_at=datetime.datetime.now(),
        status_code=200
    )
    db.session.add(new_check)
    db.session.commit()

    check_from_db = UrlCheck.query.filter_by(url_id=1).first()
    assert check_from_db is not None
    assert check_from_db.status_code == 200


def test_create_check():
    response = MockResponse(status_code=200, text=text)
    url_id = 1
    new_check = create_check(url_id, response)
    assert isinstance(new_check, UrlCheck)
    assert new_check.url_id == url_id
    assert new_check.h1_content == "Title"
    assert new_check.title_content == "Page Title"
    assert new_check.description_content == "Page description"


def test_save_check(db):
    test_url = Url(name=test_url_name)
    db.session.add(test_url)
    db.session.commit()

    with _app.app_context():
        url = Url.query.filter_by(name=test_url_name).first()
        assert url is not None

        new_check = UrlCheck(
            url_id=url.id,
            created_at=datetime.datetime.now(),
            status_code=200
        )
        save_check(new_check)

        saved_check = UrlCheck.query.filter_by(url_id=url.id).first()
        assert saved_check is not None
        assert saved_check.id == new_check.id
        assert saved_check.url_id == new_check.url_id
        assert saved_check.created_at == new_check.created_at
        assert saved_check.status_code == new_check.status_code
        assert saved_check.h1_content == new_check.h1_content
        assert saved_check.title_content == new_check.title_content
        assert saved_check.description_content == new_check.description_content


def test_add_check_handler_request_exception(client, db, mocker):
    test_url = Url(name=test_url_name)
    db.session.add(test_url)
    db.session.commit()

    mock_get = mocker.patch('requests.get')
    mock_get.side_effect = RequestException()

    response = client.post(f'/urls/{test_url.id}/checks')
    assert response.status_code == 302
    assert "Произошла ошибка при проверке" not in \
        response.get_data(as_text=True)
    assert response.location.endswith(f"/urls/{test_url.id}")


def test_get_shortened_h1_content():
    soup = BeautifulSoup(h1, html_parser)
    shortened_content = get_shortened_h1_content(soup)
    assert shortened_content == expected_value_h1


def test_get_shortened_h1_content_no_h1_tag():
    soup = BeautifulSoup(no_h1_tag, html_parser)
    shortened_content = get_shortened_h1_content(soup)
    assert shortened_content is None


def test_get_shortened_title_content():
    soup = BeautifulSoup(title, html_parser)
    shortened_content = get_shortened_title_content(soup)
    assert shortened_content == expected_value_title


def test_get_shortened_title_content_no_title_tag():
    soup = BeautifulSoup(no_title_tag, html_parser)
    shortened_content = get_shortened_title_content(soup)
    assert shortened_content is None


def test_get_shortened_description_content():
    soup = BeautifulSoup(description, html_parser)
    shortened_content = get_shortened_description_content(soup)
    assert shortened_content == expected_value_description


def test_get_shortened_description_content_no_meta_tag():
    soup = BeautifulSoup(no_h1_tag, html_parser)
    shortened_content = get_shortened_description_content(soup)
    assert shortened_content is None


if __name__ == "__main__":
    pytest.main()
