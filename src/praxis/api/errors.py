"""Map Praxis domain errors to HTTP responses."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from praxis.api.filesystem import (
    DirectoryRequiredError,
    EditorFileTooLargeError,
    FileConflictError,
    PathRejectedError,
    UnsupportedTextError,
)
from praxis.errors import (
    PraxisError,
    ScenarioSetupError,
    SessionNotFoundError,
    UnknownModuleError,
    UnknownScenarioError,
)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(SessionNotFoundError)
    async def _session_not_found(
        _request: Request, exc: SessionNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": exc.message, "code": "session_not_found"},
        )

    @app.exception_handler(UnknownModuleError)
    async def _unknown_module(
        _request: Request, exc: UnknownModuleError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": exc.message, "code": "unknown_module"},
        )

    @app.exception_handler(UnknownScenarioError)
    async def _unknown_scenario(
        _request: Request, exc: UnknownScenarioError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": exc.message, "code": "unknown_scenario"},
        )

    @app.exception_handler(ScenarioSetupError)
    async def _setup_error(_request: Request, exc: ScenarioSetupError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": exc.message, "code": "scenario_setup_error"},
        )

    @app.exception_handler(PathRejectedError)
    async def _path_rejected(_request: Request, exc: PathRejectedError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": exc.message, "code": "path_rejected"},
        )

    @app.exception_handler(FileConflictError)
    async def _file_conflict(_request: Request, exc: FileConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": exc.message, "code": "file_conflict"},
        )

    @app.exception_handler(UnsupportedTextError)
    async def _unsupported_text(
        _request: Request, exc: UnsupportedTextError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=415,
            content={"detail": exc.message, "code": "unsupported_text"},
        )

    @app.exception_handler(EditorFileTooLargeError)
    async def _too_large(
        _request: Request, exc: EditorFileTooLargeError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=413,
            content={"detail": exc.message, "code": "file_too_large"},
        )

    @app.exception_handler(DirectoryRequiredError)
    async def _not_dir(_request: Request, exc: DirectoryRequiredError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": exc.message, "code": "not_a_directory"},
        )

    @app.exception_handler(FileNotFoundError)
    async def _file_not_found(
        _request: Request, exc: FileNotFoundError
    ) -> JSONResponse:
        detail = str(exc) or "File not found"
        return JSONResponse(
            status_code=404,
            content={"detail": detail, "code": "file_not_found"},
        )

    @app.exception_handler(PraxisError)
    async def _praxis_error(_request: Request, exc: PraxisError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": exc.message, "code": "praxis_error"},
        )
