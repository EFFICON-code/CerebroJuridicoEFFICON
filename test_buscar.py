import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import procesar_pdf as backend


class BuscarTests(unittest.TestCase):
    def test_provider_paths_preserve_single_rag_and_prompt(self):
        errors = [
            RuntimeError("429 Your billing account has exceeded its monthly spending cap"),
            TimeoutError(), ConnectionError(), RuntimeError("503"),
        ]
        for gemini_error, openai_error in [(None, None), *[(e, None) for e in errors], (errors[0], RuntimeError("API"))]:
            with self.subTest(gemini_error=gemini_error, openai_error=openai_error):
                with patch.object(backend, "generar_embedding", return_value=[0.1]) as embedding, \
                     patch.object(backend.chromadb, "PersistentClient") as db, \
                     patch.object(backend.gemini_model_pro, "generate_content") as gemini, \
                     patch.object(backend, "client") as openai:
                    metadata = [{"archivo": "ley.pdf", "entidad": "NACIONAL"}]
                    collection = db.return_value.get_or_create_collection.return_value
                    collection.query.return_value = {"documents": [["Norma de prueba"]], "metadatas": [metadata]}
                    gemini.side_effect = gemini_error
                    gemini.return_value = SimpleNamespace(text="Respuesta Gemini")
                    responses = openai.with_options.return_value.responses
                    responses.create.side_effect = openai_error
                    responses.create.return_value = SimpleNamespace(output_text="Respuesta OpenAI", status="completed")
                    response = TestClient(backend.app).post("/buscar", json={
                        "query": "Analiza {{Contexto_Legal_ChromaDB}}", "contexto_busqueda": "contratación",
                        "entidad": "MUNICIPIO LOJA", "tipo_entidad": "GAD",
                    })
                    embedding.assert_called_once_with("contratación")
                    collection.query.assert_called_once()
                    gemini.assert_called_once()
                    if gemini_error is None:
                        responses.create.assert_not_called()
                    else:
                        responses.create.assert_called_once_with(model="gpt-5.6-luna", input=gemini.call_args.args[0])
                    if openai_error:
                        self.assertEqual(response.status_code, 503)
                        self.assertEqual(list(response.json()), ["error"])
                    else:
                        self.assertEqual(response.status_code, 200)
                        data = response.json()
                        self.assertTrue(data["argumentacion"])
                        self.assertEqual(data["archivos_consultados"], metadata)
                        self.assertIn("Norma de prueba", data["textos_crudos_chromadb"])
                        self.assertEqual(data["proveedor_ia"], "openai" if gemini_error else "gemini")
                        self.assertEqual(data["fallback"], gemini_error is not None)


if __name__ == "__main__":
    unittest.main()
