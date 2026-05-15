import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
from config import REGION, OPENSEARCH_ENDPOINT


def get_client() -> OpenSearch:
    creds = boto3.Session().get_credentials()
    auth = AWSV4SignerAuth(creds, REGION, "es")
    return OpenSearch(
        hosts=[{"host": OPENSEARCH_ENDPOINT, "port": 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
    )
