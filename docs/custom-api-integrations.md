# Custom API integrations

Custom API integrations support GET, POST, PUT, PATCH, DELETE, HEAD, and OPTIONS. Request settings are shared by Add Integration and Edit Integration.

## Import a cURL request

1. Select **Custom API** and enter the integration name and description.
2. Expand **Import cURL** and paste one command.
3. Select **Parse cURL**. Check the method and parameter counts.
4. Select **Apply request**. Review the URL, query parameters, headers, and body.
5. Select **Add Integration** or **Save Changes**.

Parsing runs in the browser. It does not execute the command or contact the endpoint. Apply replaces request fields, including authentication, and clears the pasted command. It retains the integration name, description, icon, and visibility.

Example:

```sh
curl --request POST 'https://api.example.com/products?category=parts' \
  --header 'Content-Type: application/json' \
  --header 'X-API-Key: replace-with-your-key' \
  --data-raw '{"search":"{{query}}","limit":5}'
```

## Agent input

`{{query}}` inserts the agent tool's query into query values, header values, body strings, or form values. JSON substitution occurs after parsing the JSON, so quotes and newlines remain valid JSON. Other values remain literal, including a JSON property named `query`.

URL paths and parameter names are fixed. The agent tool continues to accept one `query` string.

## Request fields

| Field | Behavior |
| --- | --- |
| Request URL | One absolute HTTP or HTTPS URL. Embedded credentials and fragments are rejected. |
| Query parameters | Name and value rows. Repeated names retain their order. |
| Headers | Unique names, compared without case. Credential values are masked and can be revealed. |
| Body | None, parsed JSON, raw UTF-8 text, or form URL encoded fields. |
| Bearer token | Optional. An explicit Authorization header and a bearer token cannot both be set. |
| Timeout | Positive request timeout in seconds. |

Imported Bearer authorization is placed in the token field. Other authorization schemes can use an explicit Authorization header.

## Supported cURL syntax

The importer accepts `curl` and `curl.exe`, single and double quotes, escaped quotes, and backslash line continuations. Supported options include `--url`, `-X` or `--request`, `-H` or `--header`, `-d` or `--data`, `--data-raw`, `--data-binary`, `--data-urlencode`, `--json`, `-G` or `--get`, and `-I` or `--head`. Long options can use `--option=value`. `-s`, `-S`, and `-g` are supported.

Unsupported options produce an error and leave the current request unchanged. This includes file inputs, multipart uploads, multiple URLs, shell expansion, pipelines, redirects, `--location`, `--compressed`, `--insecure`, and `-u`. Use literal header values for authentication. The versioned executor does not follow redirects.

## Stored configuration

New configurations add `request.version: 1` to the existing endpoint, method, token, timeout, and description fields. The request contains header and query rows and a body with `kind` equal to `none`, `json`, `text`, or `form`. JSON bodies store a parsed value. Text bodies store a string. Form bodies store name and value rows.

Configurations without `request` retain the legacy executor and its query injection. Saving an existing integration without changing its request preserves its original payload template and extra configuration. Deliberate request edits opt into version 1. An explicit versioned request uses the generic executor even when legacy Softnix metadata remains. MCP settings retain their existing format.
