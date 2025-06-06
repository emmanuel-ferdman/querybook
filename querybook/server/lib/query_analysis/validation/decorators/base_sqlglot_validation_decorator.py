from abc import abstractmethod
from typing import List
from sqlglot import Tokenizer
from sqlglot.tokens import Token

from lib.query_analysis.validation.base_query_validator import (
    QueryValidationResult,
    QueryValidationResultObjectType,
    QueryValidationSeverity,
)
from lib.query_analysis.validation.decorators.base_validation_decorator import (
    BaseValidationDecorator,
)
from lib.query_analysis.validation.utils import get_query_coordinate_by_index


class BaseSQLGlotValidationDecorator(BaseValidationDecorator):
    @property
    @abstractmethod
    def message(self) -> str:
        raise NotImplementedError()

    @property
    @abstractmethod
    def severity(self) -> QueryValidationSeverity:
        raise NotImplementedError()

    @property
    @abstractmethod
    def tokenizer(self) -> Tokenizer:
        raise NotImplementedError()

    def _tokenize_query(self, query: str) -> List[Token]:
        return self.tokenizer.tokenize(query)

    def _get_query_validation_result(
        self,
        query: str,
        start_index: int,
        end_index: int,
        suggestion: str = None,
        validation_result_object_type=QueryValidationResultObjectType.LINT,
        message: str = None,
    ):
        if message is None:
            message = self.message
        start_line, start_ch = get_query_coordinate_by_index(query, start_index)
        end_line, end_ch = get_query_coordinate_by_index(query, end_index)

        return QueryValidationResult(
            start_line,
            start_ch,
            self.severity,
            message,
            validation_result_object_type,
            end_line=end_line,
            end_ch=end_ch,
            suggestion=suggestion,
        )

    def validate(
        self,
        query: str,
        uid: int,
        engine_id: int,
        raw_tokens: List[Token] = None,
        **kwargs,
    ) -> List[QueryValidationResult]:
        if raw_tokens is None:
            raw_tokens = self._tokenize_query(query)
        return super(BaseSQLGlotValidationDecorator, self).validate(
            query, uid, engine_id, raw_tokens=raw_tokens, **kwargs
        )
