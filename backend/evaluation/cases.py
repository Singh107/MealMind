"""Synthetic scenarios and strict, property-based evaluation expectations."""
from typing import Literal
from pydantic import Field, model_validator
from app.schemas.recipes import Contract, RecipeGenerationRequest


class ExpectedCheck(Contract):
    constraint: str
    requested: str | float
    status: Literal['passed', 'failed', 'unknown']


class EvaluationCase(Contract):
    id: str = Field(pattern=r'^[a-z0-9-]{1,64}$')
    description: str = Field(min_length=1, max_length=500)
    request: RecipeGenerationRequest
    tags: list[str] = Field(min_length=1)
    expected_structure: Literal['valid', 'invalid'] = 'valid'
    expected_hard_restrictions: dict[str, list[str]]
    expected_constraints: list[ExpectedCheck] = Field(default_factory=list)
    fixture: Literal['normal', 'partial', 'unavailable', 'conflict', 'parse', 'schema', 'provider', 'timeout', 'state', 'omit'] = 'normal'
    expected_findings: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def restrictions_match(self):
        expected = {key: getattr(self.request, key) for key in
                    ('allergies', 'excluded_ingredients', 'dietary_preferences')}
        if self.expected_hard_restrictions != expected:
            raise ValueError('Restriction expectations must preserve the request.')
        return self


def case(identifier, tags, *, ingredients=None, fixture='normal', findings=None,
         constraints=None, **request):
    req = RecipeGenerationRequest(selected_ingredients=ingredients or ['broccoli', 'olive oil'],
                                  **request)
    return EvaluationCase(id=identifier, description='Synthetic scenario: ' + identifier.replace('-', ' '),
        request=req, tags=tags, fixture=fixture,
        expected_structure='invalid' if fixture in ('parse', 'schema', 'provider', 'timeout') else 'valid',
        expected_hard_restrictions={key: getattr(req, key) for key in
            ('allergies', 'excluded_ingredients', 'dietary_preferences')},
        expected_constraints=constraints or [], expected_findings=findings or [])


def load_cases():
    cases = [
        case('ordinary', ['basic']),
        case('one-ingredient', ['basic', 'limited'], ingredients=['broccoli']),
        case('many-ingredients', ['basic'], ingredients=['broccoli', 'carrot', 'spinach', 'olive oil', 'garlic', 'onion']),
        case('vegetarian', ['diet'], dietary_preferences=['vegetarian']),
        case('vegan', ['diet'], dietary_preferences=['vegan']),
        case('dairy-free', ['diet'], dietary_preferences=['dairy-free']),
        case('gluten-free', ['diet'], dietary_preferences=['gluten-free']),
        case('exclude-onion', ['exclusion'], excluded_ingredients=['onion']),
        case('exclude-multiple', ['exclusion'], excluded_ingredients=['onion', 'garlic']),
        case('allergy-uncertain', ['allergy'], allergies=['peanuts'], findings=['CONSTRAINT_UNKNOWN']),
        case('calorie-maximum', ['nutrition'], calorie_target=20., findings=['NUMERIC_CONSTRAINT_FAILURE'],
             constraints=[ExpectedCheck(constraint='maximum_calories', requested=20., status='failed')]),
        case('protein-minimum', ['nutrition'], protein_target=100., findings=['NUMERIC_CONSTRAINT_FAILURE']),
        case('combined-targets', ['nutrition'], calorie_target=500., protein_target=1.,
             constraints=[ExpectedCheck(constraint='maximum_calories', requested=500., status='passed'),
                          ExpectedCheck(constraint='minimum_protein', requested=1., status='passed')]),
        case('cooking-time', ['cooking'], max_cooking_time=5, findings=['NUMERIC_CONSTRAINT_FAILURE']),
        case('unusual-valid', ['edge'], ingredients=['dragon fruit', 'broccoli'], fixture='partial', findings=['NUTRITION_PARTIAL', 'UNRESOLVED_INGREDIENT']),
        case('restrictive', ['edge', 'diet'], dietary_preferences=['vegan'], allergies=['milk'], calorie_target=1., protein_target=150.),
        case('hard-conflict', ['negative', 'safety'], dietary_preferences=['vegan'], excluded_ingredients=['milk'], allergies=['milk'], fixture='conflict', findings=['HARD_CONSTRAINT_FAILURE']),
        case('nutrition-unavailable', ['negative', 'nutrition'], calorie_target=500., fixture='unavailable', findings=['NUTRITION_UNAVAILABLE', 'CONSTRAINT_UNKNOWN']),
        case('conflicting-state', ['negative', 'grounding'], fixture='state', findings=['CONFLICTING_INGREDIENT_STATE']),
        case('omitted-request', ['negative', 'grounding'], fixture='omit', findings=['REQUESTED_INGREDIENT_OMITTED']),
        case('invalid-json', ['negative', 'contract'], fixture='parse', findings=['PARSE_ERROR']),
        case('invalid-schema', ['negative', 'contract'], fixture='schema', findings=['SCHEMA_ERROR']),
        case('provider-outage', ['negative', 'provider'], fixture='provider', findings=['PROVIDER_ERROR']),
        case('provider-timeout', ['negative', 'provider'], fixture='timeout', findings=['TIMEOUT']),
    ]
    if len({c.id for c in cases}) != len(cases):
        raise ValueError('Duplicate evaluation case IDs')
    return sorted(cases, key=lambda c: c.id)
