"""Curated assembly alternatives, never general cooking/baking equivalence.
Source supports selecting cooked components for a grain bowl in equal cup portions.
No mass ratio is implied. Existing catalog remains the identity authority.
"""
from dataclasses import dataclass
from itertools import permutations

SOURCE = 'https://extension.umaine.edu/food-health/efnep/make-your-own/grain-bowl/'

@dataclass(frozen=True)
class Relationship:
    id: str
    source: str
    target: str
    role: str
    context: str = 'cooked_grain_bowl_assembly'
    ratio: float | None = 1.0
    ratio_unit: str | None = 'cup'
    support: str = 'curated_context_specific'
    source_url: str = SOURCE
    target_state: str = 'cooked'
    target_name: str | None = None

RELATIONSHIPS = tuple(Relationship(f'{role}:{a.replace(" ", "_")}:{b.replace(" ", "_")}', a, b, role)
    for role, names in [('grain_base', ('brown rice', 'white rice', 'quinoa')),
                        ('vegetable_component', ('broccoli', 'carrot', 'spinach', 'zucchini')),
                        ('bean_protein_component', ('black bean', 'chickpea'))]
    for a, b in permutations(names, 2))

DRESSING = 'https://wetlands.msuextension.org/extension/buyeatlivebetter/other_nep_resources/fact_sheets/saladdressings/Factsheet_Salad_Dressings_.pdf'
DAIRY = 'https://extension.usu.edu/boxelder/files/fn255.pdf'
# Assembly choices, not raw-food cooking instructions or nutrient equivalence.
RELATIONSHIPS += tuple(Relationship(f'protein:{a.replace(" ", "_")}:{b.replace(" ", "_")}', a, b,
    'protein_component', context='ready_component_assembly', ratio=None, ratio_unit=None)
    for a, b in permutations(('chicken breast','chicken thigh','turkey','ground beef','ground turkey','shrimp','salmon','black bean','kidney bean','chickpea'),2)
    if (a,b) not in (('black bean','chickpea'),('chickpea','black bean')))
RELATIONSHIPS += tuple(Relationship(f'dressing:{a.replace(" ", "_")}:{b.replace(" ", "_")}',a,b,
    'dressing_acid',context='uncooked_dressing',ratio=None,ratio_unit=None,source_url=DRESSING,target_state='')
    for a,b in permutations(('lemon juice','lime juice','apple cider vinegar','rice vinegar'),2))
RELATIONSHIPS += tuple(Relationship(f'oil:{a.replace(" ", "_")}:{b.replace(" ", "_")}',a,b,
    'dressing_oil',context='uncooked_dressing',source_url=DRESSING,target_state='')
    for a,b in permutations(('olive oil','vegetable oil'),2))
RELATIONSHIPS += (
    Relationship('dressing:garlic:garlic_powder','garlic','garlic powder','dressing_aromatic',
        context='uncooked_dressing',ratio=None,ratio_unit=None,source_url=DRESSING,target_state=''),
    Relationship('topping:sour_cream:yogurt','sour cream','yogurt','cold_topping',context='cold_topping',
        source_url=DAIRY,target_state='',target_name='plain yogurt'),
)
RELATIONSHIPS += tuple(Relationship(f'grain_base:{a.replace(" ", "_")}:{b.replace(" ", "_")}', a, b, 'grain_base')
    for a,b in permutations(('brown rice','white rice','quinoa','couscous','pasta'),2)
    if a in ('couscous','pasta') or b in ('couscous','pasta'))
RELATIONSHIPS += tuple(Relationship(f'saute:{a.replace(" ", "_")}:{b.replace(" ", "_")}',a,b,
    'saute_oil',context='moderate_heat_saute',ratio=None,ratio_unit=None,target_state='',
    source_url='https://extension.usu.edu/nutrition/research/navigating-dietary-fats')
    for a,b in permutations(('olive oil','canola oil'),2))
