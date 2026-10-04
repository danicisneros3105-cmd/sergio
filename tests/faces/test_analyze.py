"""Tests for scene analysis parsing and rendering (no cv2 / model needed)."""

from openjarvis.faces.analyze import (
    AnimalInfo,
    PersonInfo,
    SceneAnalysis,
    _animals_from_json,
    _parse_analysis,
    _people_from_json,
)


class TestParseAnalysis:
    def test_plain_json(self):
        data = _parse_analysis('{"personas": [], "animales": [], "resumen": "ok"}')
        assert data["resumen"] == "ok"

    def test_json_inside_markdown_fences(self):
        text = 'Claro:\n```json\n{"personas": [], "resumen": "hola"}\n```\nFin.'
        assert _parse_analysis(text)["resumen"] == "hola"

    def test_garbage_returns_empty(self):
        assert _parse_analysis("no json at all") == {}
        assert _parse_analysis("") == {}
        assert _parse_analysis("[1, 2, 3]") == {}


class TestPeopleFromJson:
    def test_full_entry(self):
        data = {
            "personas": [
                {
                    "edad_aprox": 30,
                    "rango_edad": "25-35",
                    "genero": "mujer",
                    "expresion": "sonriendo",
                }
            ]
        }
        people = _people_from_json(data)
        assert len(people) == 1
        assert people[0].age == 30
        assert people[0].gender == "mujer"

    def test_invalid_gender_becomes_indeterminado(self):
        data = {"personas": [{"genero": "helicoptero"}]}
        assert _people_from_json(data)[0].gender == "indeterminado"

    def test_bad_age_becomes_none(self):
        data = {"personas": [{"edad_aprox": "treinta"}]}
        assert _people_from_json(data)[0].age is None

    def test_non_dict_entries_skipped(self):
        data = {"personas": ["ruido", 42, {"genero": "hombre"}]}
        assert len(_people_from_json(data)) == 1


class TestAnimalsFromJson:
    def test_species_kept(self):
        data = {"animales": [{"especie": "Perro", "raza_o_tipo": "labrador"}]}
        animals = _animals_from_json(data)
        assert animals[0].species == "perro"
        assert animals[0].breed == "labrador"

    def test_empty_species_skipped(self):
        assert _animals_from_json({"animales": [{"especie": ""}]}) == []


class TestSceneAnalysis:
    def test_species_summary(self):
        scene = SceneAnalysis(
            people=[PersonInfo(age=30, gender="mujer")],
            animals=[AnimalInfo("gato"), AnimalInfo("gato"), AnimalInfo("dragon")],
        )
        assert scene.species == ["humano", "gato", "otro_animal"]

    def test_empty_scene(self):
        assert SceneAnalysis().species == ["nadie"]
        assert "No veo a nadie" in SceneAnalysis().to_text()

    def test_describe_person(self):
        person = PersonInfo(
            name="Sergio", age=28, age_range="25-30", gender="hombre",
            expression="sonriendo",
        )
        text = person.describe()
        assert "Sergio" in text and "~28" in text and "hombre" in text

    def test_to_dict_shape(self):
        scene = SceneAnalysis(people=[PersonInfo(gender="mujer")])
        data = scene.to_dict()
        assert data["especies"] == ["humano"]
        assert data["personas"][0]["genero"] == "mujer"
