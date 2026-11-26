# 24. Install polish: forgiving Bearer header, one doctor run

Two small fixes found while setting up a second instance (the demo) on the same server.

## Bearer header

`app/bearer.py` reads the token from `Authorization: Bearer <token>` for both the capture token
(`app/auth.py`) and the MCP secret (`app/mcp_auth.py`). It now accepts:

- the scheme in any letter case (`Bearer`, `bearer`, `BEARER`), as HTTP specifies (RFC 9110),
- spaces or a line break around the token, which easily slip in when a token is copied from a
  terminal into an iOS Shortcut or a connector form.

Still rejected: a missing header, another scheme (`Basic ...`), an empty token, a token with a space
inside, and of course a wrong token (compared in constant time, as before). The error messages are
unchanged (`missing token`, `wrong token`, `missing or wrong MCP secret`).

## setup.sh: wait for the service, run the doctor once

Before, setup.sh ran `python -m app.doctor` up to six times, 10 s apart. A problem the doctor finds,
such as a wrong API key, does not go away by waiting, so a bad key cost a minute of identical reports.
Now setup.sh waits until the service answers `/health` inside its container (up to 30 tries, 2 s apart),
then runs the doctor once. If it finds problems, setup.sh says how to rerun it after fixing `.env`, and
still prints the URLs and tokens at the end.

## Tests

- `tests/test_bearer.py`: accepted and rejected spellings, `/capture` with a lowercase scheme and a
  trailing space, the MCP secret check.
- `tests/test_setup_script.py`: the readiness check comes before the doctor, which runs exactly once;
  a failing doctor is reported once and the tokens are still printed (the docker stub fails the doctor
  with `STUB_DOCTOR_EXIT=1`).
- Not covered by a test: the message when the service never answers (it would take a minute of waiting).
