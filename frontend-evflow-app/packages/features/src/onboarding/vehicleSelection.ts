import type { EVModelApiItem } from '@evflow/shared';

export const OTHER_BRAND = 'Other';

export function brandOf(model: EVModelApiItem): string {
  return model.make?.trim() || OTHER_BRAND;
}

export function filterVehicleModels(
  models: EVModelApiItem[],
  selectedBrand: string | null,
  query: string,
): EVModelApiItem[] {
  const normalizedQuery = query.trim().toLocaleLowerCase();

  return models.filter((model) => {
    if (selectedBrand && brandOf(model) !== selectedBrand) return false;
    if (!normalizedQuery) return selectedBrand !== null;

    return [model.make, model.model, model.name]
      .filter((value): value is string => Boolean(value))
      .some((value) => value.toLocaleLowerCase().includes(normalizedQuery));
  });
}
