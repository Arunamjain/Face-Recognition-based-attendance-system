import os
import logging
from typing import Optional, Dict, Any, List
from backend.config import FIREBASE_CREDENTIALS_PATH, FIREBASE_PROJECT_ID

logger = logging.getLogger("backend.firebase")

# In-memory document and collection simulation for mock testing and offline mode
class MockDocumentSnapshot:
    def __init__(self, doc_id: str, data: Optional[Dict[str, Any]]):
        self.id = doc_id
        self._data = dict(data) if data is not None else None
        self.exists = data is not None

    def to_dict(self) -> Optional[Dict[str, Any]]:
        return dict(self._data) if self._data is not None else None


class MockDocumentReference:
    def __init__(self, collection: 'MockCollectionReference', doc_id: str):
        self.collection = collection
        self.id = doc_id

    def get(self) -> MockDocumentSnapshot:
        data = self.collection.store.get(self.id)
        return MockDocumentSnapshot(self.id, data)

    def set(self, data: Dict[str, Any], merge: bool = False):
        if merge and self.id in self.collection.store:
            self.collection.store[self.id].update(data)
        else:
            self.collection.store[self.id] = dict(data)

    def update(self, data: Dict[str, Any]):
        if self.id not in self.collection.store:
            raise KeyError(f"Document {self.id} does not exist in collection {self.collection.name}")
        self.collection.store[self.id].update(data)

    def delete(self):
        self.collection.store.pop(self.id, None)


class MockQuery:
    def __init__(self, collection: 'MockCollectionReference', filters: List[tuple]):
        self.collection = collection
        self.filters = list(filters)

    def where(self, field: str, op: str, value: Any) -> 'MockQuery':
        new_filters = list(self.filters)
        new_filters.append((field, op, value))
        return MockQuery(self.collection, new_filters)

    def stream(self):
        for doc_id, data in list(self.collection.store.items()):
            match = True
            for field, op, val in self.filters:
                doc_val = data.get(field)
                if op == "==" and doc_val != val:
                    match = False
                    break
                elif op == ">=" and (doc_val is None or doc_val < val):
                    match = False
                    break
                elif op == "<=" and (doc_val is None or doc_val > val):
                    match = False
                    break
            if match:
                yield MockDocumentSnapshot(doc_id, data)


class MockCollectionReference:
    def __init__(self, name: str, root_store: Dict[str, Dict[str, Dict[str, Any]]]):
        self.name = name
        self._root_store = root_store
        if name not in self._root_store:
            self._root_store[name] = {}
        self.store = self._root_store[name]

    def document(self, doc_id: str) -> MockDocumentReference:
        return MockDocumentReference(self, doc_id)

    def where(self, field: str, op: str, value: Any) -> MockQuery:
        return MockQuery(self, [(field, op, value)])

    def stream(self):
        for doc_id, data in list(self.store.items()):
            yield MockDocumentSnapshot(doc_id, data)


class MockFirestoreClient:
    """Mock Firestore client providing the Firestore SDK interface for testing/offline use."""
    def __init__(self):
        self._collections: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def collection(self, name: str) -> MockCollectionReference:
        return MockCollectionReference(name, self._collections)

    def clear(self):
        self._collections.clear()


# Global client holders
_firebase_initialized = False
_firestore_client = None
_is_mock = False


def initialize_firebase(force_mock: bool = False):
    """
    Initializes the Firebase Admin SDK or sets up a mock client for local testing.
    """
    global _firebase_initialized, _firestore_client, _is_mock

    if force_mock:
        logger.info("Initializing in-memory Mock Firestore client (Testing mode).")
        _firestore_client = MockFirestoreClient()
        _is_mock = True
        _firebase_initialized = True
        return _firestore_client

    if _firestore_client is not None:
        return _firestore_client

    # Check for serviceAccountKey.json
    cred_path = FIREBASE_CREDENTIALS_PATH
    if os.path.exists(cred_path):
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore

            if not firebase_admin._apps:
                cred = credentials.Certificate(cred_path)
                options = {"projectId": FIREBASE_PROJECT_ID} if FIREBASE_PROJECT_ID else None
                firebase_admin.initialize_app(cred, options)
                logger.info(f"Firebase Admin SDK initialized successfully with credentials from: {cred_path}")

            _firestore_client = firestore.client()
            _is_mock = False
            _firebase_initialized = True
            return _firestore_client
        except Exception as e:
            logger.warning(f"Failed to initialize Firebase Admin with credentials ({e}). Falling back to Mock Firestore.")
            _firestore_client = MockFirestoreClient()
            _is_mock = True
            _firebase_initialized = True
            return _firestore_client
    else:
        logger.info(
            f"Firebase service account file '{cred_path}' not found. "
            "Falling back to Mock Firestore client for local testing/development."
        )
        _firestore_client = MockFirestoreClient()
        _is_mock = True
        _firebase_initialized = True
        return _firestore_client


def get_db():
    """Returns the active Firestore client (live or mock)."""
    global _firestore_client
    if _firestore_client is None:
        return initialize_firebase()
    return _firestore_client


def is_mock_db() -> bool:
    """Returns True if the current client is a mock."""
    return _is_mock


def reset_mock_db():
    """Resets all data in mock client (useful in test fixtures)."""
    global _firestore_client
    if isinstance(_firestore_client, MockFirestoreClient):
        _firestore_client.clear()
