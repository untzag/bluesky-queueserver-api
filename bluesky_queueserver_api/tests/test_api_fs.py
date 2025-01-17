import asyncio
import getpass
from io import StringIO
import os
import pytest
import time as ttime

from bluesky_queueserver import generate_zmq_keys

from .common import re_manager_cmd  # noqa: F401
from .common import fastapi_server_fs  # noqa: F401
from .common import (
    set_qserver_zmq_address,
    set_qserver_zmq_public_key,
    _is_async,
    _select_re_manager_api,
    instantiate_re_api_class,
)

from ..comm_base import RequestParameterError


# fmt: off
@pytest.mark.parametrize("option", ["params", "ev", "default_addr"])
@pytest.mark.parametrize("library", ["THREADS", "ASYNC"])
@pytest.mark.parametrize("protocol", ["ZMQ", "HTTP"])
# fmt: on
def test_ReManagerAPI_parameters_01(
    monkeypatch, re_manager_cmd, fastapi_server_fs, protocol, library, option  # noqa: F811
):
    """
    ReManagerComm_ZMQ_Threads and ReManagerComm_ZMQ_Async,
    ReManagerComm_HTTP_Threads and ReManagerComm_HTTP_Async:
    Check that the server addresses are properly set with parameters and EVs.
    ZMQ: ``zmq_control_addr``, ``zmq_info_addr``, ``QSERVER_ZMQ_CONTROL_ADDRESS``,
    ``QSERVER_ZMQ_INFO_ADDRESS``. HTTP: ``http_server_uri``, ``QSERVER_HTTP_SERVER_URI``.
    """
    zmq_control_addr_server = "tcp://*:60616"
    zmq_control_addr_client = "tcp://localhost:60616"
    zmq_info_addr_server = "tcp://*:60617"
    zmq_info_addr_client = "tcp://localhost:60617"
    http_host = "localhost"
    http_port = 60611
    http_server_uri = f"http://{http_host}:{http_port}"

    zmq_public_key, zmq_private_key = generate_zmq_keys()

    set_qserver_zmq_address(monkeypatch, zmq_server_address=zmq_control_addr_client)
    set_qserver_zmq_public_key(monkeypatch, server_public_key=zmq_public_key)
    monkeypatch.setenv("QSERVER_ZMQ_PRIVATE_KEY_FOR_SERVER", zmq_private_key)
    re_manager_cmd(
        [
            "--zmq-publish-console=ON",
            f"--zmq-control-addr={zmq_control_addr_server}",
            f"--zmq-info-addr={zmq_info_addr_server}",
        ]
    )

    if protocol == "HTTP":
        monkeypatch.setenv("QSERVER_ZMQ_CONTROL_ADDRESS", zmq_control_addr_client)
        monkeypatch.setenv("QSERVER_ZMQ_INFO_ADDRESS", zmq_info_addr_client)
        monkeypatch.setenv("QSERVER_ZMQ_PUBLIC_KEY", zmq_public_key)
        fastapi_server_fs(http_server_host=http_host, http_server_port=http_port)
        if option in "params":
            params = {"http_server_uri": http_server_uri}
        elif option == "ev":
            params = {}
            monkeypatch.setenv("QSERVER_HTTP_SERVER_URI", http_server_uri)
        elif option == "default_addr":
            params = {}
        else:
            assert False, "Unknown option: {option!r}"
    elif protocol == "ZMQ":
        if option == "params":
            params = {
                "zmq_control_addr": zmq_control_addr_client,
                "zmq_info_addr": zmq_info_addr_client,
                "zmq_public_key": zmq_public_key,
            }
        elif option == "ev":
            params = {}
            monkeypatch.setenv("QSERVER_ZMQ_CONTROL_ADDRESS", zmq_control_addr_client)
            monkeypatch.setenv("QSERVER_ZMQ_INFO_ADDRESS", zmq_info_addr_client)
            monkeypatch.setenv("QSERVER_ZMQ_PUBLIC_KEY", zmq_public_key)
        elif option == "default_addr":
            params = {}
        else:
            assert False, "Unknown option: {option!r}"
    else:
        assert False, "Unknown protocol: {protocol!r}"

    rm_api_class = _select_re_manager_api(protocol, library)

    if not _is_async(library):
        RM = instantiate_re_api_class(rm_api_class, **params)
        if option == "default_addr":
            # ZMQ - RequestTimeoutError, HTTP - HTTPRequestError
            with pytest.raises((RM.RequestTimeoutError, RM.HTTPRequestError)):
                RM.status()
        else:
            RM.status()
            RM.console_monitor.enable()
            RM.environment_open()
            RM.wait_for_idle()
            RM.environment_close()
            RM.wait_for_idle()
            RM.console_monitor.disable()

            text = RM.console_monitor.text()
            assert "RE Environment is ready" in text, text

        RM.close()

    else:

        async def testing():
            RM = instantiate_re_api_class(rm_api_class, **params)
            if option == "default_addr":
                # ZMQ - RequestTimeoutError, HTTP - HTTPRequestError
                with pytest.raises((RM.RequestTimeoutError, RM.HTTPRequestError)):
                    await RM.status()
            else:
                await RM.status()
                RM.console_monitor.enable()
                await RM.environment_open()
                await RM.wait_for_idle()
                await RM.environment_close()
                await RM.wait_for_idle()
                RM.console_monitor.disable()

                text = await RM.console_monitor.text()
                assert "RE Environment is ready" in text, text

            await RM.close()

        asyncio.run(testing())


# fmt: off
@pytest.mark.parametrize("tout, tout_login, tset, tset_login", [
    (0.5, 10, 0.5, 10),
    (None, None, 5.0, 60.0),  # Default values
    (0, 0, 0, 0),  # Disables timeout by default
])
@pytest.mark.parametrize("library", ["THREADS", "ASYNC"])
@pytest.mark.parametrize("protocol", ["HTTP"])
# fmt: on
def test_ReManagerAPI_parameters_02(protocol, library, tout, tout_login, tset, tset_login):
    """
    classes ReManagerComm_HTTP_Threads and ReManagerComm_HTTP_Async:
    Test that 'timeout' and 'timeout_login' are set correctly.
    """
    rm_api_class = _select_re_manager_api(protocol, library)

    if not _is_async(library):
        RM = instantiate_re_api_class(rm_api_class, timeout=tout, timeout_login=tout_login)
        assert RM._timeout == tset
        assert RM._timeout_login == tset_login
        RM.close()

    else:

        async def testing():
            RM = instantiate_re_api_class(rm_api_class, timeout=tout, timeout_login=tout_login)
            assert RM._timeout == tset
            assert RM._timeout_login == tset_login
            await RM.close()

        asyncio.run(testing())


# fmt: off
@pytest.mark.parametrize("library", ["THREADS", "ASYNC"])
@pytest.mark.parametrize("protocol", ["HTTP"])
# fmt: on
def test_send_request_1(re_manager_cmd, fastapi_server_fs, protocol, library):  # noqa: F811
    """
    ``send_request`` API: basic functionality and error handling (for HTTP requests).
    """
    re_manager_cmd()
    fastapi_server_fs()

    rm_api_class = _select_re_manager_api(protocol, library)

    if not _is_async(library):
        RM = instantiate_re_api_class(rm_api_class)

        status = RM.status()
        status2 = RM.send_request(method="status")
        assert status2 == status
        status3 = RM.send_request(method=("GET", "/api/status"))
        assert status3 == status

        with pytest.raises(RM.RequestParameterError, match="Unknown method"):
            RM.send_request(method="abc")

        with pytest.raises(RM.RequestParameterError, match="must be a string or an iterable"):
            RM.send_request(method=10)

        for method in (
            ("GET", "/api/status", "aaa"),
            ("GET",),
            (10, "/api/status"),
            ("GET", {}),
            (10, 20),
        ):
            print(f"Testing method: {method}")
            with pytest.raises(RM.RequestParameterError, match="must consist of 2 string elements"):
                RM.send_request(method=method)

        RM.close()
    else:

        async def testing():
            RM = instantiate_re_api_class(rm_api_class)

            status = await RM.status()
            status2 = await RM.send_request(method="status")
            assert status2 == status
            status3 = await RM.send_request(method=("GET", "/api/status"))
            assert status3 == status

            with pytest.raises(RM.RequestParameterError, match="Unknown method"):
                await RM.send_request(method="abc")

            with pytest.raises(RM.RequestParameterError, match="must be a string or an iterable"):
                await RM.send_request(method=10)

            for method in (
                ("GET", "/api/status", "aaa"),
                ("GET",),
                (10, "/api/status"),
                ("GET", {}),
                (10, 20),
            ):
                print(f"Testing method: {method}")
                with pytest.raises(RM.RequestParameterError, match="must consist of 2 string elements"):
                    await RM.send_request(method=method)

            await RM.close()

        asyncio.run(testing())


# fmt: off
@pytest.mark.parametrize("library", ["THREADS", "ASYNC"])
@pytest.mark.parametrize("protocol", ["HTTP"])
# fmt: on
def test_send_request_2(fastapi_server_fs, protocol, library):  # noqa: F811
    """
    ``send_request`` API: timeout (for HTTP requests).
    """
    fastapi_server_fs()
    rm_api_class = _select_re_manager_api(protocol, library)

    if not _is_async(library):
        RM = instantiate_re_api_class(rm_api_class)

        # No timeout
        status = RM.send_request(method=("GET", "/api/test/server/sleep"), params={"time": 3})
        assert status["success"] is True

        # Set timeout for the given request
        with pytest.raises(RM.RequestTimeoutError):
            RM.send_request(method=("GET", "/api/test/server/sleep"), params={"time": 3}, timeout=1)

        # Use the defaut timeout
        with pytest.raises(RM.RequestTimeoutError):
            RM.send_request(method=("GET", "/api/test/server/sleep"), params={"time": RM._timeout + 1})

        RM.close()
    else:

        async def testing():
            RM = instantiate_re_api_class(rm_api_class)

            # No timeout
            status = await RM.send_request(method=("GET", "/api/test/server/sleep"), params={"time": 3})
            assert status["success"] is True

            # Set timeout for the given request
            with pytest.raises(RM.RequestTimeoutError):
                await RM.send_request(method=("GET", "/api/test/server/sleep"), params={"time": 3}, timeout=1)

            # Use the defaut timeout
            with pytest.raises(RM.RequestTimeoutError):
                await RM.send_request(method=("GET", "/api/test/server/sleep"), params={"time": RM._timeout + 1})

            await RM.close()

        asyncio.run(testing())


# Configuration file for 'toy' authentication provider. The passwords are explicitly listed.
config_toy_yml = """
uvicorn:
    host: localhost
    port: 60610
authentication:
    providers:
        - provider: toy
          authenticator: bluesky_httpserver.authenticators:DictionaryAuthenticator
          args:
              users_to_passwords:
                  alice: alice_password
                  bob: bob_password
                  cara: cara_password
    qserver_admins:
        - provider: toy
          id: alice
"""


# Configuration file for 'toy' authentication provider. The passwords are explicitly listed.
config_toy_yml_short_token_expiration = """
uvicorn:
    host: localhost
    port: 60610
authentication:
    providers:
        - provider: toy
          authenticator: bluesky_httpserver.authenticators:DictionaryAuthenticator
          args:
              users_to_passwords:
                  alice: alice_password
                  bob: bob_password
                  cara: cara_password
    qserver_admins:
        - provider: toy
          id: alice
    access_token_max_age: 2
    refresh_token_max_age: 600
    session_max_age: 1000
"""


def _setup_server_with_config_file(*, config_file_str, tmpdir, monkeypatch):
    """
    Creates config file for the server in ``tmpdir/config/`` directory and
    sets up the respective environment variable. Sets ``tmpdir`` as a current directory.
    """
    config_fln = "config_httpserver.yml"
    config_dir = os.path.join(tmpdir, "config")
    config_path = os.path.join(config_dir, config_fln)
    os.makedirs(config_dir)
    with open(config_path, "wt") as f:
        f.writelines(config_file_str)

    monkeypatch.setenv("QSERVER_HTTP_SERVER_CONFIG", config_path)
    monkeypatch.chdir(tmpdir)

    return config_path


# fmt: off
@pytest.mark.parametrize("default_provider", [True, False])
@pytest.mark.parametrize("use_kwargs", [True, False])
@pytest.mark.parametrize("library", ["THREADS", "ASYNC"])
@pytest.mark.parametrize("protocol", ["HTTP"])
# fmt: on
def test_login_1(
    tmpdir,
    monkeypatch,
    re_manager_cmd,  # noqa: F811
    fastapi_server_fs,  # noqa: F811
    protocol,
    library,
    default_provider,
    use_kwargs,
):
    """
    ``login`` API (for HTTP requests). Basic functionality.
    """
    re_manager_cmd()
    _setup_server_with_config_file(config_file_str=config_toy_yml, tmpdir=tmpdir, monkeypatch=monkeypatch)
    fastapi_server_fs()
    rm_api_class = _select_re_manager_api(protocol, library)

    if not _is_async(library):
        params = {"http_auth_provider": "/toy/token"} if default_provider else {}
        RM = instantiate_re_api_class(rm_api_class, **params)

        # Make sure access does not work without authentication
        with pytest.raises(RM.HTTPClientError, match="401"):
            RM.status()

        login_args, login_kwargs = [], {"password": "bob_password"}
        if not default_provider:
            login_kwargs.update({"provider": "/toy/token"})
        if use_kwargs:
            login_kwargs.update({"username": "bob"})
        else:
            login_args.extend(["bob"])

        token_info = RM.login(*login_args, **login_kwargs)
        auth_key = RM.auth_key
        assert isinstance(auth_key, tuple), auth_key
        assert auth_key[0] == token_info["access_token"]
        assert auth_key[1] == token_info["refresh_token"]

        # Now make sure that access works
        RM.status()

        RM.close()
    else:

        async def testing():
            params = {"http_auth_provider": "/toy/token"} if default_provider else {}
            RM = instantiate_re_api_class(rm_api_class, **params)

            # Make sure access does not work without authentication
            with pytest.raises(RM.HTTPClientError, match="401"):
                await RM.status()

            login_args, login_kwargs = [], {"password": "bob_password"}
            if not default_provider:
                login_kwargs.update({"provider": "/toy/token"})
            if use_kwargs:
                login_kwargs.update({"username": "bob"})
            else:
                login_args.extend(["bob"])

            token_info = await RM.login(*login_args, **login_kwargs)
            auth_key = RM.auth_key
            assert isinstance(auth_key, tuple), auth_key
            assert auth_key[0] == token_info["access_token"]
            assert auth_key[1] == token_info["refresh_token"]

            # Now make sure that access works
            await RM.status()

            await RM.close()

        asyncio.run(testing())


# fmt: off
@pytest.mark.parametrize("interactive_username", [False, True])
@pytest.mark.parametrize("library", ["THREADS", "ASYNC"])
@pytest.mark.parametrize("protocol", ["HTTP"])
# fmt: on
def test_login_2(
    tmpdir,
    monkeypatch,
    re_manager_cmd,  # noqa: F811
    fastapi_server_fs,  # noqa: F811
    protocol,
    library,
    interactive_username,
):
    """
    ``login`` API (for HTTP requests). Interactive input of username and password.
    """
    re_manager_cmd()
    _setup_server_with_config_file(config_file_str=config_toy_yml, tmpdir=tmpdir, monkeypatch=monkeypatch)
    monkeypatch.setattr(getpass, "getpass", lambda: "bob_password")
    fastapi_server_fs()
    rm_api_class = _select_re_manager_api(protocol, library)

    if not _is_async(library):
        RM = instantiate_re_api_class(rm_api_class, http_auth_provider="/toy/token")

        # Make sure access does not work without authentication
        with pytest.raises(RM.HTTPClientError, match="401"):
            RM.status()

        if interactive_username:
            monkeypatch.setattr("sys.stdin", StringIO("bob\n"))
            RM.login()
        else:
            RM.login("bob")

        # Now make sure that access works
        RM.status()

        RM.close()
    else:

        async def testing():
            RM = instantiate_re_api_class(rm_api_class, http_auth_provider="/toy/token")

            # Make sure access does not work without authentication
            with pytest.raises(RM.HTTPClientError, match="401"):
                await RM.status()

            if interactive_username:
                monkeypatch.setattr("sys.stdin", StringIO("bob\n"))
                await RM.login()
            else:
                await RM.login("bob")

            # Now make sure that access works
            await RM.status()

            await RM.close()

        asyncio.run(testing())


# fmt: off
@pytest.mark.parametrize("library", ["THREADS", "ASYNC"])
@pytest.mark.parametrize("protocol", ["HTTP"])
# fmt: on
def test_login_3_fail(
    tmpdir,
    monkeypatch,
    re_manager_cmd,  # noqa: F811
    fastapi_server_fs,  # noqa: F811
    protocol,
    library,
):
    """
    ``login`` API (for HTTP requests). Failing cases due to invalid parameters.
    """
    re_manager_cmd()
    _setup_server_with_config_file(config_file_str=config_toy_yml, tmpdir=tmpdir, monkeypatch=monkeypatch)
    fastapi_server_fs()
    rm_api_class = _select_re_manager_api(protocol, library)

    invalid_providers = [
        (10, rm_api_class.RequestParameterError, "must be a string or None"),
        ("", rm_api_class.RequestParameterError, "is an empty string"),
    ]

    invalid_username_password = [
        ("bob", 10, rm_api_class.RequestParameterError, "'password' is not string"),
        ("bob", "", rm_api_class.RequestParameterError, "'password' is an empty string"),
        (10, "bob-password", rm_api_class.RequestParameterError, "'username' is not string"),
        ("", "bob-password", rm_api_class.RequestParameterError, "'username' is an empty string"),
        ("bob", "rand_pwd", rm_api_class.HTTPClientError, "401: Incorrect username or password"),
        ("rand_user", "bob-password", rm_api_class.HTTPClientError, "401: Incorrect username or password"),
        ("rand_user", "rand_pwd", rm_api_class.HTTPClientError, "401: Incorrect username or password"),
    ]

    if not _is_async(library):

        for provider, except_type, msg in invalid_providers:
            with pytest.raises(except_type, match=msg):
                RM = instantiate_re_api_class(rm_api_class, http_auth_provider=provider)

        RM = instantiate_re_api_class(rm_api_class, http_auth_provider="/toy/token")

        # Make sure access does not work without authentication
        with pytest.raises(RM.HTTPClientError, match="401"):
            RM.status()

        # Invalid provider
        for provider, except_type, msg in invalid_providers:
            with pytest.raises(except_type, match=msg):
                RM.login("bob", password="bob_password", provider=provider)

        # Invalid username, password or both
        for username, password, except_type, msg in invalid_username_password:
            with pytest.raises(except_type, match=msg):
                RM.login(username, password=password)

        # Make sure access does not work without authentication
        with pytest.raises(RM.HTTPClientError, match="401"):
            RM.status()

        RM.close()
    else:

        async def testing():
            RM = instantiate_re_api_class(rm_api_class, http_auth_provider="/toy/token")

            for provider, except_type, msg in invalid_providers:
                with pytest.raises(except_type, match=msg):
                    RM = instantiate_re_api_class(rm_api_class, http_auth_provider=provider)

            RM = instantiate_re_api_class(rm_api_class, http_auth_provider="/toy/token")

            # Make sure access does not work without authentication
            with pytest.raises(RM.HTTPClientError, match="401"):
                await RM.status()

            # Invalid provider
            for provider, except_type, msg in invalid_providers:
                with pytest.raises(except_type, match=msg):
                    await RM.login("bob", password="bob_password", provider=provider)

            # Invalid username, password or both
            for username, password, except_type, msg in invalid_username_password:
                with pytest.raises(except_type, match=msg):
                    await RM.login(username, password=password)

            # Make sure access does not work without authentication
            with pytest.raises(RM.HTTPClientError, match="401"):
                await RM.status()

            await RM.close()

        asyncio.run(testing())


# fmt: off
@pytest.mark.parametrize("token_as_param", [False, True])
@pytest.mark.parametrize("library", ["THREADS", "ASYNC"])
@pytest.mark.parametrize("protocol", ["HTTP"])
# fmt: on
def test_session_refresh_1(
    tmpdir,
    monkeypatch,
    re_manager_cmd,  # noqa: F811
    fastapi_server_fs,  # noqa: F811
    protocol,
    library,
    token_as_param,
):
    """
    ``session_refresh`` API (for HTTP requests). Interactive input of username and password.
    """
    re_manager_cmd()
    _setup_server_with_config_file(config_file_str=config_toy_yml, tmpdir=tmpdir, monkeypatch=monkeypatch)
    monkeypatch.setattr(getpass, "getpass", lambda: "bob_password")
    fastapi_server_fs()
    rm_api_class = _select_re_manager_api(protocol, library)

    if not _is_async(library):
        RM = instantiate_re_api_class(rm_api_class, http_auth_provider="/toy/token")

        # Make sure access does not work without authentication
        with pytest.raises(RM.HTTPClientError, match="401"):
            RM.status()

        RM.login("bob", password="bob_password")
        RM.status()

        if token_as_param:
            refresh_token = RM.auth_key[1]
            RM.set_authorization_key()  # Clear all tokens
            response = RM.session_refresh(refresh_token=refresh_token)
        else:
            RM.set_authorization_key(refresh_token=RM.auth_key[1])  # Clear the access token
            response = RM.session_refresh()

        assert response["access_token"] == RM.auth_key[0]
        assert response["refresh_token"] == RM.auth_key[1]

        RM.status()

        # Invalid refresh token
        if token_as_param:
            RM.set_authorization_key()  # Clear all tokens
            with pytest.raises(RM.HTTPClientError, match="401"):
                RM.session_refresh(refresh_token="invalidtoken")
        else:
            RM.set_authorization_key(refresh_token="invalidtoken")  # Clear the access token
            with pytest.raises(RM.HTTPClientError, match="401"):
                RM.session_refresh()

        RM.close()
    else:

        async def testing():
            RM = instantiate_re_api_class(rm_api_class, http_auth_provider="/toy/token")

            # Make sure access does not work without authentication
            with pytest.raises(RM.HTTPClientError, match="401"):
                await RM.status()

            await RM.login("bob", password="bob_password")
            await RM.status()

            if token_as_param:
                refresh_token = RM.auth_key[1]
                RM.set_authorization_key()  # Clear all tokens
                response = await RM.session_refresh(refresh_token=refresh_token)
            else:
                RM.set_authorization_key(refresh_token=RM.auth_key[1])  # Clear the access token
                response = await RM.session_refresh()

            assert response["access_token"] == RM.auth_key[0]
            assert response["refresh_token"] == RM.auth_key[1]

            await RM.status()

            # Invalid refresh token
            if token_as_param:
                RM.set_authorization_key()  # Clear all tokens
                with pytest.raises(RM.HTTPClientError, match="401"):
                    await RM.session_refresh(refresh_token="invalidtoken")
            else:
                RM.set_authorization_key(refresh_token="invalidtoken")  # Clear the access token
                with pytest.raises(RM.HTTPClientError, match="401"):
                    await RM.session_refresh()

            await RM.close()

        asyncio.run(testing())


# fmt: off
@pytest.mark.parametrize("token, except_type, msg", [
    (10, RequestParameterError, "'refresh_token' must be a string or None"),
    ("", RequestParameterError, "'refresh_token' is an empty string"),
    (None, RequestParameterError, "'refresh_token' is not set"),
])
@pytest.mark.parametrize("library", ["THREADS", "ASYNC"])
@pytest.mark.parametrize("protocol", ["HTTP"])
# fmt: on
def test_session_refresh_2_fail(protocol, library, token, except_type, msg):
    """
    ``session_refresh`` API (for HTTP requests). Failing cases due to invalid parameters.
    """
    rm_api_class = _select_re_manager_api(protocol, library)

    if not _is_async(library):
        RM = instantiate_re_api_class(rm_api_class, http_auth_provider="/toy/token")

        with pytest.raises(except_type, match=msg):
            RM.session_refresh(refresh_token=token)

        RM.close()
    else:

        async def testing():
            RM = instantiate_re_api_class(rm_api_class, http_auth_provider="/toy/token")

            with pytest.raises(except_type, match=msg):
                await RM.session_refresh(refresh_token=token)

            await RM.close()

        asyncio.run(testing())


# fmt: off
@pytest.mark.parametrize("library", ["THREADS", "ASYNC"])
@pytest.mark.parametrize("protocol", ["HTTP"])
# fmt: on
def test_session_refresh_3(
    tmpdir,
    monkeypatch,
    re_manager_cmd,  # noqa: F811
    fastapi_server_fs,  # noqa: F811
    protocol,
    library,
):
    """
    ``session_refresh`` API (for HTTP requests). Test that the session is automatically refreshed
    as the access token expires. Consider the server with very short session expiration time and
    then repeatedly try to load status from the server.
    """
    re_manager_cmd()
    _setup_server_with_config_file(
        config_file_str=config_toy_yml_short_token_expiration, tmpdir=tmpdir, monkeypatch=monkeypatch
    )
    # _setup_server_with_config_file(config_file_str=config_toy_yml, tmpdir=tmpdir, monkeypatch=monkeypatch)
    monkeypatch.setattr(getpass, "getpass", lambda: "bob_password")
    fastapi_server_fs()
    rm_api_class = _select_re_manager_api(protocol, library)

    if not _is_async(library):
        RM = instantiate_re_api_class(rm_api_class, http_auth_provider="/toy/token")

        RM.login("bob", password="bob_password")

        n_expirations = 0
        for _ in range(10):
            try:
                RM.send_request(method="status", auto_refresh_session=False)
            except Exception:
                n_expirations += 1

            RM.status()
            ttime.sleep(1)

        assert n_expirations > 0

        RM.close()
    else:

        async def testing():
            RM = instantiate_re_api_class(rm_api_class, http_auth_provider="/toy/token")

            await RM.login("bob", password="bob_password")

            n_expirations = 0
            for _ in range(10):
                try:
                    await RM.send_request(method="status", auto_refresh_session=False)
                except Exception:
                    n_expirations += 1

                await RM.status()
                await asyncio.sleep(1)

            await RM.close()

            assert n_expirations > 0

        asyncio.run(testing())
