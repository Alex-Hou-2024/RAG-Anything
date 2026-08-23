from api.services.capabilities import detect_capabilities
def test_capabilities_shape():
 c=detect_capabilities().public();assert set(c)=={'mineru','libreoffice'}
