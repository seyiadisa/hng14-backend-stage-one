from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

auth_rate_limit = limiter.shared_limit("10/minute", scope="auth")
profile_rate_limit = limiter.shared_limit("60/minute", scope="profiles")
