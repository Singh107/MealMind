import asyncio
import re
from uuid import uuid4
from app.core.errors import GenerationError
from app.schemas.recipes import GeneratedRecipe, RecipeIngredient, NutritionInfo
from app.schemas.intelligence import RecipeIntelligence, CalculatedNutrition, IngredientNutrition
from app.services.normalization import IngredientNormalizationService, normalize_unit
from app.services.constraints import ConstraintService
from app.services.pantry import PantryService, pantry_identity
from app.services.repair import hard
from app.services.substitution_knowledge import RELATIONSHIPS
from app.services.ingredient_catalog import clean_name, DISCOVERY_ALIASES

def substitution_identity(name):
    identity = pantry_identity(name)
    normalized = IngredientNormalizationService().normalize(name, 1, 'g')
    base = clean_name(normalized.name)
    if normalized.food_state == 'canned':
        base = re.sub(r' drained solids$', '', base)
    # Discovery identity is permitted here without asserting composition safety.
    entry = DISCOVERY_ALIASES.get(base)
    if entry and normalized.reason != 'Conflicting food preparation states.':
        identity = {**identity, 'normalized_name': entry['canonical'], 'identity_status': 'recognized'}
    return identity

class SubstitutionService:
    def __init__(self, nutrition=None, timeout=25):
        self.nutrition, self.timeout = nutrition, timeout
        self.normalizer, self.constraints = IngredientNormalizationService(), ConstraintService()

    def evidence(self, recipe):
        sources = [IngredientNutrition(ingredient_index=i, ingredient=self.normalizer.normalize(x.name,x.quantity,x.unit), status='unavailable') for i,x in enumerate(recipe.ingredients)]
        return RecipeIntelligence(calculated_nutrition=CalculatedNutrition(servings=recipe.servings,ingredient_count=len(sources)),
            nutrition_status='unavailable',nutrition_sources=sources,unmatched_ingredients=[x.name for x in recipe.ingredients])

    def context_supported(self, recipe, index, relation=None):
        item = recipe.ingredients[index]
        identity = substitution_identity(item.name)
        context = relation.context if relation else 'cooked_grain_bowl_assembly'
        text = ' '.join(recipe.instructions)
        commands = re.sub(r'\bcooked\b', '', text, flags=re.I)
        if re.search(r'\b(?:bake|baking|preserve|canning|pickle|ferment|deep.fry)\w*\b', recipe.title+' '+commands, re.I):
            return False
        if context == 'moderate_heat_saute':
            return (identity['identity_status']=='recognized' and identity['food_state'] is None and
                not re.search(r'\b(?:high heat|smok\w*|sear\w*|deep.fry\w*)\b',text,re.I) and
                any(identity['normalized_name'] in clean_name(step) and
                    re.search(r'\b(?:medium|low)(?:[- ]low)? heat\b',step,re.I) and
                    re.search(r'\b(?:saute|sauté|heat)\b',step,re.I) for step in recipe.instructions))
        if context in ('uncooked_dressing', 'cold_topping'):
            if re.search(r'\b(?:cook|heat|boil|simmer|fry|roast|saute|steam|grill|microwave)\w*\b',commands,re.I):
                return False
            return (identity['identity_status']=='recognized' and identity['food_state'] in (None,'raw') and
                bool(re.search(r'\b(?:dressing|vinaigrette|salad|dip|topping)\b',recipe.title+' '+text,re.I)) and
                any(re.search(r'\b(?:mix|whisk|combine|stir|drizzle|top|add|shake)\b',step,re.I) and
                    identity['normalized_name'] in clean_name(step) for step in recipe.instructions))
        if context == 'ready_component_assembly':
            if identity['food_state'] not in ('cooked','canned') or (identity['food_state']=='canned' and identity['normalized_name'] not in ('black bean','kidney bean','chickpea')):
                return False
            if re.search(r'\b(?:cook|heat|boil|simmer|fry|roast|saute|steam|grill|microwave)\w*\b',commands,re.I):
                return False
            return bool(re.search(r'\b(?:bowl|salad|wrap)\b',recipe.title,re.I)) and any(
                re.search(r'\b(?:add|layer|combine|assemble|place|top|mix|toss)\b',step,re.I) and
                identity['normalized_name'] in clean_name(step) for step in recipe.instructions)
        if identity['identity_status'] != 'recognized' or identity['food_state'] != 'cooked':
            return False
        if not re.search(r'\b(?:grain|rice|quinoa) bowls?\b', recipe.title, re.I):
            return False
        if re.search(r'\b(?:cook|boil|simmer|fry|bake|roast|saute|steam|grill|microwave|heat)\w*\b', ' '.join(recipe.instructions), re.I):
            # Already-cooked ingredient mentions are permitted, but cooking commands are not.
            commands = re.sub(r'\bcooked\b', '', ' '.join(recipe.instructions), flags=re.I)
            if re.search(r'\b(?:cook|boil|simmer|fry|bake|roast|saute|steam|grill|microwave|heat)\w*\b',commands,re.I):
                return False
        return any(re.search(r'\b(?:add|layer|combine|assemble|place|top|mix)\b', step,re.I) and
                   re.search(r'(?<!\w)'+re.escape(item.name)+r'(?!\w)',step,re.I) for step in recipe.instructions)

    def variant(self, recipe, index, target, quantity, unit, target_state='cooked'):
        variant = recipe.model_copy(deep=True)
        old = recipe.ingredients[index].name
        new = (target_state + ' ' + target).strip()
        variant.ingredients[index] = RecipeIngredient(name=new, quantity=quantity, unit=unit)
        normalized = self.normalizer.normalize(old).name
        source_identity = substitution_identity(old)['normalized_name']
        names = {old, normalized, source_identity}
        entry = DISCOVERY_ALIASES.get(source_identity)
        if entry:
            names.update(entry['aliases'])
        pattern = r'(?<!\w)(?:' + '|'.join(re.escape(x) for x in sorted(names,key=len,reverse=True)) + r')(?!\w)'
        replace = lambda text: re.sub(pattern, lambda match: new if match.group().casefold()==old.casefold() else target, text, flags=re.I)
        variant.instructions = [replace(step) for step in recipe.instructions]
        variant.title, variant.description = replace(recipe.title), replace(recipe.description)
        variant.dietary_tags, variant.potential_allergens = [], []
        variant.nutrition = NutritionInfo(calories=None,protein=None,carbohydrates=None,fat=None)
        return variant

    def browse(self, payload, restrictions, pantry=None, pantry_state='not_requested'):
        recipe, index = payload.recipe, payload.ingredient_index
        item = recipe.ingredients[index]
        base = dict(original_ingredient=item.model_dump(),ingredient_index=index,candidates=[],blocked_count=0,
                    pantry_state=pantry_state,limitations=['Context-specific alternatives; review flavor and instructions. Quantity sufficiency and allergy safety are not certified.'])
        identity = substitution_identity(item.name)
        if not any(r.source == identity['normalized_name'] and self.context_supported(recipe,index,r) for r in RELATIONSHIPS):
            return {**base,'status':'unsupported_context','message':'No reliable substitute available for this ingredient and recipe context.'}
        others = {substitution_identity(x.name)['normalized_name'] for i,x in enumerate(recipe.ingredients) if i != index}
        for relation in RELATIONSHIPS:
            if not self.context_supported(recipe,index,relation):
                continue
            if relation.source != identity['normalized_name'] or relation.target == relation.source or relation.target in others:
                continue
            variant = self.variant(recipe,index,relation.target_name or relation.target,item.quantity,item.unit,relation.target_state)
            checked = self.constraints.validate(restrictions,variant,self.evidence(variant))
            restrictions_results = [r for r in checked.constraint_results if hard(r)]
            if any(r.status=='failed' for r in restrictions_results):
                base['blocked_count'] += 1
                continue
            uncertain = any(r.status=='unknown' for r in restrictions_results)
            availability = 'not_known'
            if pantry is not None:
                fit = PantryService.compare([variant.ingredients[index]],pantry)
                availability = fit.ingredients[0].status
            known_ratio = relation.ratio is not None and normalize_unit(item.unit) == relation.ratio_unit
            base['candidates'].append(dict(relationship_id=relation.id,name=variant.ingredients[index].name,
                functional_role=relation.role,context=relation.context,support=relation.support,source_url=relation.source_url,
                ratio=relation.ratio if known_ratio else None,ratio_unit='cup' if known_ratio else None,
                compatibility='uncertain' if uncertain else 'compatible',availability=availability,
                reasons=[{'code':'role','text':'Context-specific '+relation.role.replace('_',' ')+'. Flavor and texture may change; review the instructions.'},
                    {'code':'quantity','text':'Use the same cup amount in this context.' if known_ratio else 'A direct quantity ratio is not established; enter an amount for the preview.'},
                    {'code':'restrictions','text':'Compatibility could not be fully verified.' if uncertain else 'No known conflict in the current supported restriction checks; not allergy certification.'},
                    {'code':'evaluation','text':'Nutrition and constraints will be recalculated in the preview.'}]))
        base['candidates'].sort(key=lambda c:(c['compatibility']=='uncertain',c['availability']!='available',c['relationship_id']))
        return {**base,'status':'ready' if base['candidates'] else 'no_candidates',
            'message':'Choose an alternative to preview.' if base['candidates'] else 'No alternatives remain after context, duplicate and restriction checks.'}

    async def evaluate(self, recipe, restrictions, deadline):
        normal = [self.normalizer.normalize(x.name,x.quantity,x.unit) for x in recipe.ingredients]
        report = await self.nutrition.calculate(normal,recipe.servings,remaining_seconds=max(0,deadline-asyncio.get_running_loop().time()))
        return self.constraints.validate(restrictions,recipe,report)

    async def preview(self,payload,restrictions):
        found = self.browse(payload,restrictions)
        option = next((x for x in found['candidates'] if x['relationship_id']==payload.relationship_id),None)
        if option is None:
            raise GenerationError('substitution_not_allowed','This alternative is unsupported or conflicts with current restrictions.',422,False)
        relation = next(x for x in RELATIONSHIPS if x.id==payload.relationship_id)
        original = payload.recipe.model_copy(deep=True)
        item = original.ingredients[payload.ingredient_index]
        if (payload.quantity is None) != (payload.unit is None):
            raise GenerationError('substitution_quantity_required','Enter both quantity and unit.',422,False)
        if payload.quantity is None:
            if option['ratio'] is None:
                raise GenerationError('substitution_quantity_required','A ratio is unknown. Enter a quantity and supported unit.',422,False)
            quantity, unit = item.quantity * option['ratio'], 'cup'
        else:
            quantity, unit = payload.quantity, normalize_unit(payload.unit)
            if unit is None:
                raise GenerationError('substitution_quantity_required','Choose a supported unit.',422,False)
        variant = self.variant(original,payload.ingredient_index,relation.target_name or relation.target,quantity,unit,relation.target_state)
        deadline = asyncio.get_running_loop().time()+self.timeout
        try:
            async with asyncio.timeout(self.timeout):
                before = await self.evaluate(original,restrictions,deadline)
                after = await self.evaluate(variant,restrictions,deadline)
        except TimeoutError:
            raise GenerationError('substitution_timeout','Preview timed out. Your original recipe is unchanged.',504,True) from None
        except GenerationError:
            raise
        except Exception:
            raise GenerationError('substitution_unavailable','Nutrition preview is unavailable. Your original recipe is unchanged.',503,True) from None
        can_use = not any(hard(r) and r.status != 'passed' for r in after.constraint_results)
        original_generated = GeneratedRecipe(**original.model_dump(),id=uuid4(),recipe_version_id=uuid4())
        final_generated = GeneratedRecipe(**variant.model_dump(),id=uuid4(),recipe_version_id=uuid4())
        return dict(restrictions=restrictions.model_dump(mode='json'),original_recipe=original_generated.model_dump(mode='json'),final_recipe=final_generated.model_dump(mode='json'),
            before_intelligence=before.model_dump(mode='json'),after_intelligence=after.model_dump(mode='json'),can_use=can_use,
            change=dict(ingredient_index=payload.ingredient_index,before=item.model_dump(),after=variant.ingredients[payload.ingredient_index].model_dump(),
                relationship_id=relation.id,reason='User-selected '+relation.role.replace('_',' ')+' alternative; review flavor and instructions.'),
            message='Review the recalculated evidence before choosing this version. No general improvement is claimed.' if can_use else 'Hard restriction compatibility is unresolved or failed. Original recipe retained; this version cannot be used.')
