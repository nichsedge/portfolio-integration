import time
import hashlib
import base64
from urllib.parse import quote
import jwt
from fake_useragent import UserAgent
import asyncio
import httpx
from typing import Any, Dict, List, Optional, Union
import logging

logger = logging.getLogger(__name__)


def get_expire_time(token: str) -> Optional[int]:
    """
    Get the expiration time from a JWT token.

    Args:
        token: The JWT token string

    Returns:
        The expiration timestamp as an integer or None if invalid
    """
    try:
        decoded = jwt.decode(token, options={"verify_signature": False})
        return decoded.get("exp")
    except jwt.DecodeError as e:
        logger.warning(f"Failed to decode JWT token: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error decoding JWT token: {e}")
        return None


class KSEIClient:
    def __init__(
        self,
        auth_store=None,
        username: str = "",
        password: str = "",
        plain_password: bool = True,
        timeout: float = 30.0,
    ):
        """
        Initialize the KSEIClient.

        Args:
            auth_store: Optional storage for authentication tokens
            username: KSEI username
            password: KSEI password
            plain_password: Whether password is plain text (True) or already hashed (False)
            timeout: Request timeout in seconds
        """
        self.base_url = "https://akses.ksei.co.id/service"
        self.base_referer = "https://akses.ksei.co.id"
        self.auth_store = auth_store
        self.username = username
        self.password = password
        self.plain_password = plain_password
        self.ua = UserAgent()
        self.timeout = timeout
        self._token: Optional[str] = None
        self._lock = asyncio.Lock()
        self._client: Optional[httpx.Client] = None

        # Validate required parameters
        if not username or not password:
            logger.warning(
                "Username and password should be provided for proper functionality"
            )

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def _build_password_hash_params(self) -> tuple[str, str]:
        """
        Build the parameters for password hashing.

        Returns:
            A tuple of (password_sha1, encoded_param)
        """
        if not self.plain_password:
            return self.password, ""

        password_sha1 = hashlib.sha1(self.password.encode()).hexdigest()
        timestamp = int(time.time())
        param = f"{password_sha1}@@!!@@{timestamp}"
        encoded_param = base64.b64encode(param.encode()).decode()
        return password_sha1, encoded_param

    def _hash_password(self, client: httpx.Client) -> str:
        """
        Hash the password using the KSEI API.

        Args:
            client: HTTP client instance

        Returns:
            The hashed password

        Raises:
            httpx.HTTPStatusError: If the API request fails
            KeyError: If the response doesn't contain the expected data
        """
        if not self.plain_password:
            logger.debug("Using pre-hashed password")
            return self.password

        _, encoded_param = self._build_password_hash_params()
        url = f"{self.base_url}/activation/generated?param={quote(encoded_param)}"

        logger.debug(f"Requesting password hash from: {url}")
        response = client.get(
            url, headers={"Referer": self.base_referer, "User-Agent": self.ua.random}
        )
        response.raise_for_status()

        data = response.json()
        hashed_password = data["data"][0]["pass"]
        logger.debug("Successfully obtained password hash")
        return hashed_password

    async def _hash_password_async(self, client: httpx.AsyncClient) -> str:
        """
        Asynchronously hash the password using the KSEI API.

        Args:
            client: Async HTTP client instance

        Returns:
            The hashed password

        Raises:
            httpx.HTTPStatusError: If the API request fails
            KeyError: If the response doesn't contain the expected data
        """
        if not self.plain_password:
            logger.debug("Using pre-hashed password")
            return self.password

        _, encoded_param = self._build_password_hash_params()
        url = f"{self.base_url}/activation/generated?param={quote(encoded_param)}"

        logger.debug(f"Requesting password hash from: {url}")
        response = await client.get(
            url, headers={"Referer": self.base_referer, "User-Agent": self.ua.random}
        )
        response.raise_for_status()

        data = response.json()
        hashed_password = data["data"][0]["pass"]
        logger.debug("Successfully obtained password hash")
        return hashed_password

    def _build_login_data(self, hashed_password: str) -> Dict[str, str]:
        """
        Build the login data payload.

        Args:
            hashed_password: The hashed password

        Returns:
            Dictionary containing login data
        """
        return {
            "username": self.username,
            "password": hashed_password,
            "id": "1",
            "appType": "web",
        }

    def _make_login_request(
        self, client: httpx.Client, login_data: Dict[str, str]
    ) -> str:
        """
        Make the login request and return the token.

        Args:
            client: HTTP client instance
            login_data: Login data payload

        Returns:
            The authentication token

        Raises:
            httpx.HTTPStatusError: If the login request fails
            KeyError: If the response doesn't contain the expected data
        """
        url = f"{self.base_url}/login?lang=id"
        headers = {
            "Referer": self.base_referer,
            "User-Agent": self.ua.random,
            "Content-Type": "application/json",
        }

        logger.debug(f"Attempting login for user: {self.username}")
        response = client.post(url, json=login_data, headers=headers)
        response.raise_for_status()

        data = response.json()
        token = data["validation"]

        logger.info(f"Successfully logged in user: {self.username}")
        return token

    async def _make_login_request_async(
        self, client: httpx.AsyncClient, login_data: Dict[str, str]
    ) -> str:
        """
        Make the asynchronous login request and return the token.

        Args:
            client: Async HTTP client instance
            login_data: Login data payload

        Returns:
            The authentication token

        Raises:
            httpx.HTTPStatusError: If the login request fails
            KeyError: If the response doesn't contain the expected data
        """
        url = f"{self.base_url}/login?lang=id"
        headers = {
            "Referer": self.base_referer,
            "User-Agent": self.ua.random,
            "Content-Type": "application/json",
        }

        logger.debug(f"Attempting login for user: {self.username}")
        response = await client.post(url, json=login_data, headers=headers)
        response.raise_for_status()

        data = response.json()
        token = data["validation"]

        logger.info(f"Successfully logged in user: {self.username}")
        return token

    def _login(self, client: httpx.Client) -> str:
        """
        Authenticate with the KSEI API.

        Args:
            client: HTTP client instance

        Returns:
            The authentication token
        """
        hashed_password = self._hash_password(client)
        login_data = self._build_login_data(hashed_password)
        token = self._make_login_request(client, login_data)

        if self.auth_store:
            self.auth_store.set(self.username, token)

        return token

    async def _login_async(self, client: httpx.AsyncClient) -> str:
        """
        Asynchronously authenticate with the KSEI API.

        Args:
            client: Async HTTP client instance

        Returns:
            The authentication token
        """
        hashed_password = await self._hash_password_async(client)
        login_data = self._build_login_data(hashed_password)
        token = await self._make_login_request_async(client, login_data)

        if self.auth_store:
            self.auth_store.set(self.username, token)

        return token

    def _get_token(self) -> str:
        client = self._get_client()
        if not self.auth_store:
            return self._login(client)

        token = self.auth_store.get(self.username)
        if not token:
            return self._login(client)

        expire_time = get_expire_time(token)
        if not expire_time or expire_time < time.time():
            return self._login(client)

        return token

    async def _get_token_async(self, client: httpx.AsyncClient) -> str:
        if self._token:
            expire_time = get_expire_time(self._token)
            if expire_time and expire_time > time.time():
                return self._token

        async with self._lock:
            # Check again in case another task just refreshed the token
            if self._token:
                expire_time = get_expire_time(self._token)
                if expire_time and expire_time > time.time():
                    return self._token

            token = None
            if self.auth_store:
                token = self.auth_store.get(self.username)

            if token:
                expire_time = get_expire_time(token)
                if expire_time and expire_time > time.time():
                    self._token = token
                    return token

            self._token = await self._login_async(client)
            return self._token

    def get(self, path: str) -> Union[Dict, List]:
        """
        Make a GET request to the KSEI API.

        Args:
            path: API endpoint path

        Returns:
            The JSON response data

        Raises:
            httpx.HTTPStatusError: If the request fails
            httpx.RequestError: If there's a network error
            ValueError: If the response is not valid JSON
        """
        if not path.startswith("/"):
            path = f"/{path}"

        client = self._get_client()
        token = self._get_token()
        url = f"{self.base_url}{path}"

        headers = {
            "Referer": self.base_referer,
            "User-Agent": self.ua.random,
            "Authorization": f"Bearer {token}",
        }

        logger.debug(f"Making GET request to: {url}")
        try:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            logger.debug(f"Successfully retrieved data from: {url}")
            return data
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error {e.response.status_code} requesting {url}: {e.response.text}"
            )
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error for {url}: {str(e)}")
            raise
        except ValueError as e:
            logger.error(f"JSON decode error for {url}: {str(e)}")
            raise ValueError(f"Invalid JSON response from {url}") from e

    def get_portfolio_summary(self) -> Union[Dict, List]:
        return self.get("/myportofolio/summary")

    def get_cash_balances(self) -> Union[Dict, List]:
        return self.get("/myportofolio/summary-detail/kas")

    def get_equity_balances(self) -> Union[Dict, List]:
        return self.get("/myportofolio/summary-detail/ekuitas")

    def get_mutual_fund_balances(self) -> Union[Dict, List]:
        return self.get("/myportofolio/summary-detail/reksadana")

    def get_bond_balances(self) -> Union[Dict, List]:
        return self.get("/myportofolio/summary-detail/obligasi")

    def get_other_balances(self) -> Union[Dict, List]:
        return self.get("/myportofolio/summary-detail/lainnya")

    def get_global_identity(self) -> Union[Dict, List]:
        return self.get("/myaccount/global-identity/")

    async def get_async(
        self, client: httpx.AsyncClient, path: str
    ) -> Union[Dict, List]:
        """
        Make an asynchronous GET request to the KSEI API.

        Args:
            client: Async HTTP client instance
            path: API endpoint path

        Returns:
            The JSON response data

        Raises:
            httpx.HTTPStatusError: If the request fails
            httpx.RequestError: If there's a network error
            ValueError: If the response is not valid JSON
        """
        if not path.startswith("/"):
            path = f"/{path}"

        token = await self._get_token_async(client)
        url = f"{self.base_url}{path}"

        headers = {
            "Referer": self.base_referer,
            "User-Agent": self.ua.random,
            "Authorization": f"Bearer {token}",
        }

        logger.debug(f"Making async GET request to: {url}")
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            logger.debug(f"Successfully retrieved data from: {url}")
            return data
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error {e.response.status_code} requesting {url}: {e.response.text}"
            )
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error for {url}: {str(e)}")
            raise
        except ValueError as e:
            logger.error(f"JSON decode error for {url}: {str(e)}")
            raise ValueError(f"Invalid JSON response from {url}") from e

    async def get_all_portfolios_async(self) -> Dict[str, Optional[Union[Dict, List]]]:
        """
        Asynchronously fetch all portfolio types in parallel.

        Returns:
            A dictionary mapping portfolio types to their data or None if an error occurred
        """
        portfolio_types = {
            "cash": "/myportofolio/summary-detail/kas",
            "equity": "/myportofolio/summary-detail/ekuitas",
            "mutual_fund": "/myportofolio/summary-detail/reksadana",
            "bond": "/myportofolio/summary-detail/obligasi",
            "other": "/myportofolio/summary-detail/lainnya",
        }

        logger.info("Starting to fetch all portfolio types asynchronously")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            tasks = []
            for portfolio_type, path in portfolio_types.items():
                task = asyncio.create_task(
                    self.get_async(client, path), name=portfolio_type
                )
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

        portfolio_data: Dict[str, Optional[Union[Dict, List]]] = {}
        for task, result in zip(tasks, results):
            portfolio_type = task.get_name()
            if isinstance(result, Exception):
                logger.error(f"Error fetching {portfolio_type}: {result!r}")
                portfolio_data[portfolio_type] = None
            else:
                logger.info(f"Successfully fetched {portfolio_type} data")
                portfolio_data[portfolio_type] = result

        logger.info("Completed fetching all portfolio types")
        return portfolio_data
