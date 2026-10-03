"""TLS trust for standalone macOS builds; never disable certificate checks."""
import ssl

def tls_context():
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())
