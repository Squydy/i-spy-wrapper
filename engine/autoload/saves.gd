extends Node
## Progress persistence. v1 keeps one auto-save per game (user://saves/<id>.json);
## the API is slot-agnostic so modern multi-slot saves can be layered on later.

const DIR := "user://saves"

var game_id: String = ""
var data: Dictionary = {}


func open(id: String) -> void:
	game_id = id
	DirAccess.make_dir_recursive_absolute(DIR)
	var loaded = Library.load_json(_path())
	data = loaded if loaded is Dictionary else {}
	if not data.has("found"):
		data["found"] = {}
	if not data.has("solved"):
		data["solved"] = []
	if not data.has("hunt"):
		data["hunt"] = "A"


func _path() -> String:
	return DIR.path_join("%s.json" % game_id)


func save() -> void:
	if game_id == "":
		return
	var f := FileAccess.open(_path(), FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(data, "\t"))
		f.close()


func reset() -> void:
	data = {"found": {}, "solved": [], "hunt": data.get("hunt", "A")}
	save()


func get_hunt() -> String:
	return str(data.get("hunt", "A"))


func set_hunt(h: String) -> void:
	data["hunt"] = h
	save()


func set_screen(id: String) -> void:
	data["screen"] = id
	save()


func get_screen() -> String:
	return str(data.get("screen", ""))


static func key(screen: String, hunt: String) -> String:
	return "%s:%s" % [screen, hunt]


func found_items(screen: String, hunt: String) -> Array:
	return data["found"].get(key(screen, hunt), [])


func is_found(screen: String, hunt: String, item: String) -> bool:
	return item in found_items(screen, hunt)


func mark_found(screen: String, hunt: String, item: String) -> void:
	var k := key(screen, hunt)
	var arr: Array = data["found"].get(k, [])
	if item not in arr:
		arr.append(item)
	data["found"][k] = arr
	save()


func is_solved(screen: String, hunt: String) -> bool:
	return key(screen, hunt) in data["solved"]


func mark_solved(screen: String, hunt: String) -> void:
	var k := key(screen, hunt)
	if k not in data["solved"]:
		data["solved"].append(k)
	save()


func solved_count(hunt: String) -> int:
	var n := 0
	for k in data["solved"]:
		if str(k).ends_with(":" + hunt):
			n += 1
	return n
