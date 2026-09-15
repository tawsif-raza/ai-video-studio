"""A hand-rolled, in-memory fake of the small slice of the boto3 S3 client
API storage/s3_project_sync.py actually calls - the same "fake, not mock"
convention this codebase already uses for LLM clients and controllers
(tests/web_api/conftest.py) rather than pulling in a library like moto."""
import hashlib
from pathlib import Path


class FakeS3Client:
    def __init__(self):
        self.objects: dict[str, bytes] = {}  # key -> content

    def upload_file(self, filename: str, bucket: str, key: str) -> None:
        self.objects[key] = Path(filename).read_bytes()

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        if key not in self.objects:
            raise FileNotFoundError(key)  # shaped like botocore's ClientError enough for these tests
        Path(filename).write_bytes(self.objects[key])

    def head_object(self, Bucket: str, Key: str) -> dict:
        if Key not in self.objects:
            raise KeyError(Key)
        # Real S3's ETag is (for non-multipart uploads) the content's MD5 -
        # derived from content here too, so two uploads of identical bytes
        # compare equal and any content change is reliably detected by
        # ensure_local()'s staleness check.
        return {"ContentLength": len(self.objects[Key]), "ETag": hashlib.md5(self.objects[Key]).hexdigest()}

    def list_objects_v2(self, **kwargs) -> dict:
        prefix = kwargs.get("Prefix", "")
        delimiter = kwargs.get("Delimiter")
        matching = sorted(k for k in self.objects if k.startswith(prefix))

        if delimiter:
            common_prefixes = set()
            contents = []
            for key in matching:
                rest = key[len(prefix):]
                if delimiter in rest:
                    common_prefixes.add(prefix + rest.split(delimiter, 1)[0] + delimiter)
                else:
                    contents.append(key)
            return {
                "Contents": [{"Key": k} for k in contents],
                "CommonPrefixes": [{"Prefix": p} for p in sorted(common_prefixes)],
                "IsTruncated": False,
            }

        return {
            "Contents": [{"Key": k} for k in matching],
            "IsTruncated": False,
        }
