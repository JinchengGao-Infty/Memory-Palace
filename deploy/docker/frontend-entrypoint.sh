#!/usr/bin/env sh
set -eu

template_path="/etc/nginx/templates/default.conf.template"
target_path="/etc/nginx/conf.d/default.conf"

mcp_api_key="${MCP_API_KEY:-}"
csp_connect_src="${FRONTEND_CSP_CONNECT_SRC:-'self'}"
carriage_return="$(printf '\r')"
backtick="$(printf '\140')"

# POSIX shell variables cannot preserve NUL bytes. Reject the remaining
# control characters and a narrow set of config-hostile shell characters that
# we do not expect in normal API keys.
case "${mcp_api_key}" in
  *"$carriage_return"*|*"$backtick"*|*'
'*)
    echo "MCP_API_KEY contains unsupported control characters." >&2
    exit 1
    ;;
esac

stripped_controls="$(
  printf '%s' "${mcp_api_key}" | LC_ALL=C tr -d '[:cntrl:]'
)"
if [ "${stripped_controls}" != "${mcp_api_key}" ]; then
  echo "MCP_API_KEY contains unsupported control characters." >&2
  exit 1
fi

case "${csp_connect_src}" in
  *"$carriage_return"*|*"$backtick"*|*'
'*|*';'*|*'"'*)
    echo "FRONTEND_CSP_CONNECT_SRC contains unsupported characters." >&2
    exit 1
    ;;
esac

stripped_csp_controls="$(
  printf '%s' "${csp_connect_src}" | LC_ALL=C tr -d '[:cntrl:]'
)"
if [ "${stripped_csp_controls}" != "${csp_connect_src}" ]; then
  echo "FRONTEND_CSP_CONNECT_SRC contains unsupported characters." >&2
  exit 1
fi

escaped_mcp_api_key="$(printf '%s' "${mcp_api_key}" | sed 's/[\\\"$]/\\&/g')"
escaped_csp_connect_src="$(printf '%s' "${csp_connect_src}" | sed 's/[\\\"$]/\\&/g')"
export MCP_API_KEY_NGINX_ESCAPED="${escaped_mcp_api_key}"
export FRONTEND_CSP_CONNECT_SRC_NGINX_ESCAPED="${escaped_csp_connect_src}"

envsubst '${MCP_API_KEY_NGINX_ESCAPED} ${FRONTEND_CSP_CONNECT_SRC_NGINX_ESCAPED}' < "${template_path}" > "${target_path}"
nginx -t

exec nginx -g 'daemon off;'
