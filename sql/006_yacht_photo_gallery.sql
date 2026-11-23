-- Attach the supplied, named yacht photos to the matching demo boats.
-- This is safe to run on every startup: existing photo paths are not duplicated
-- and an administrator's later cover selection is preserved.
CREATE TEMP TABLE yacht_gallery_import ON COMMIT DROP AS
SELECT * FROM (VALUES
  ('Морской бриз 01','assets/boats/gallery/sea_breeze_01.jpg',1),
  ('Морской бриз 06','assets/boats/gallery/sea_breeze_06.jpg',1),
  ('Морской бриз 11','assets/boats/gallery/sea_breeze_11.jpg',1),
  ('Морской бриз 16','assets/boats/gallery/sea_breeze_16.jpg',1),
  ('Морской бриз 21','assets/boats/gallery/sea_breeze_21.jpg',1),
  ('Синяя лагуна 02','assets/boats/gallery/blue_lagoon_02.jpg',1),
  ('Синяя лагуна 07','assets/boats/gallery/blue_lagoon_07.jpg',1),
  ('Синяя лагуна 12','assets/boats/gallery/blue_lagoon_12.jpg',1),
  ('Синяя лагуна 17','assets/boats/gallery/blue_lagoon_17.jpg',1),
  ('Синяя лагуна 22','assets/boats/gallery/blue_lagoon_22.jpg',1),
  ('Белый парус 03','assets/boats/gallery/white_sail_03.jpg',1),
  ('Белый парус 08','assets/boats/gallery/white_sail_08.jpg',1),
  ('Белый парус 13','assets/boats/gallery/white_sail_13.jpg',1),
  ('Белый парус 18','assets/boats/gallery/white_sail_18.jpg',1),
  ('Белый парус 23','assets/boats/gallery/white_sail_23.jpg',1),
  ('Атлантика 04','assets/boats/gallery/atlantic_04.jpg',1),
  ('Атлантика 09','assets/boats/gallery/atlantic_09.jpg',1),
  ('Атлантика 09','assets/boats/gallery/atlantic_09_b.jpg',2),
  ('Атлантика 14','assets/boats/gallery/atlantic_14.jpg',1),
  ('Атлантика 19','assets/boats/gallery/atlantic_19.jpg',1),
  ('Атлантика 24','assets/boats/gallery/atlantic_24.jpg',1),
  ('Лазурный берег 05','assets/boats/gallery/azure_coast_05.jpg',1),
  ('Лазурный берег 10','assets/boats/gallery/azure_coast_10.jpg',1),
  ('Лазурный берег 15','assets/boats/gallery/azure_coast_15.jpg',1),
  ('Лазурный берег 20','assets/boats/gallery/azure_coast_20.jpg',1),
  ('Лазурный берег 25','assets/boats/gallery/azure_coast_25.jpg',1)
) AS source(boat_name,image_path,photo_order);

-- Retire the old generic SVG cover so the imported photo can become the cover.
UPDATE boat_images image
SET is_cover=false
FROM boats boat
WHERE image.boat_id=boat.boat_id
  AND image.is_cover
  AND image.image_path LIKE 'assets/boats/%.svg'
  AND EXISTS (SELECT 1 FROM yacht_gallery_import gallery WHERE gallery.boat_name=boat.name);

-- Reuse seeded placeholder rows for the first three photos, keeping the gallery
-- compact and replacing the generic illustrations for these boats.
UPDATE boat_images image
SET image_path=gallery.image_path,
    caption=boat.name || ' · фото ' || gallery.photo_order,
    alt_text='Фотография яхты ' || boat.name,
    sort_order=gallery.photo_order,
    source_note='Фотография из архива пользователя',
    is_cover=false
FROM yacht_gallery_import gallery
JOIN boats boat ON boat.name=gallery.boat_name
WHERE image.boat_id=boat.boat_id
  AND image.sort_order=gallery.photo_order
  AND image.image_path LIKE 'assets/boats/%.svg';

-- Remove any remaining generic illustrations from boats that now have real photos.
DELETE FROM boat_images image
USING boats boat
WHERE image.boat_id=boat.boat_id
  AND image.image_path LIKE 'assets/boats/%.svg'
  AND EXISTS (SELECT 1 FROM yacht_gallery_import gallery WHERE gallery.boat_name=boat.name);

INSERT INTO boat_images(boat_id,image_path,caption,alt_text,sort_order,is_cover,source_note)
SELECT boat.boat_id,gallery.image_path,
       boat.name || ' · фото ' || gallery.photo_order,
       'Фотография яхты ' || boat.name,
       gallery.photo_order,false,'Фотография из архива пользователя'
FROM yacht_gallery_import gallery
JOIN boats boat ON boat.name=gallery.boat_name
WHERE NOT EXISTS (
  SELECT 1 FROM boat_images existing
  WHERE existing.boat_id=boat.boat_id AND existing.image_path=gallery.image_path
);

-- Assign the first supplied photo as cover only when the boat has no cover yet.
UPDATE boat_images image
SET is_cover=true
FROM yacht_gallery_import gallery
JOIN boats boat ON boat.name=gallery.boat_name
WHERE gallery.photo_order=1
  AND image.boat_id=boat.boat_id
  AND image.image_path=gallery.image_path
  AND NOT EXISTS (
    SELECT 1 FROM boat_images current_cover
    WHERE current_cover.boat_id=boat.boat_id AND current_cover.is_cover
  );

DROP TABLE yacht_gallery_import;
