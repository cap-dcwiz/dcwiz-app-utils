# dcwiz-app-utils
Backend Utils for Building DCWiz Application

## dcwiz-app-token-helper 

Sometimes you need to get a token for a user to test your app. This is a simple helper to get a token for a user.
To use this helper, create an `.env` file in the root of the project and add the following:

```bash
AUTH_BASE={auth url} #for example, "https://auth.experimental.rda.ai"
AUTH_CLIENT_ID=dcwiz-client
AUTH_CLIENT_SECRET={your client secret}
```

Then run the following command:
```bash
$ poetry run dcwiz-app-token-helper 
```

A server will be started on port 10010. 
You can go to `http://localhost:10010/login` to login with your credentials. The user profile and token will be 
displayed on the page if the login is successful.

You also go to `http://localhost:10010/docs` for more helper endpoints.