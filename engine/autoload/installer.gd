extends Node
## Drives the Python tools (tools/ispytools) from the launcher: install from ISO, (re)extract.
## Runs the CLI on a worker thread and reports its output when it finishes.

signal started(label: String)
signal finished(ok: bool, output: String)

var busy: bool = false
var _thread: Thread


func python_command() -> String:
	var opt := Library.cmdline_option("python")
	return opt if opt != "" else "python"


func install_iso(iso_path: String, with_video: bool = true) -> void:
	var args: Array = ["install", iso_path]
	if not with_video:
		args.append("--no-video")
	_run("Installing %s" % iso_path.get_file(), args)


func extract_game(game_id: String) -> void:
	_run("Extracting %s" % game_id, ["extract", game_id])


func _run(label: String, cli_args: Array) -> void:
	if busy:
		return
	busy = true
	started.emit(label)
	var args: Array = ["-m", "ispytools", "--games", Library.games_root()]
	args.append_array(cli_args)
	_thread = Thread.new()
	_thread.start(_worker.bind(args))


func _worker(args: Array) -> void:
	var output: Array = []
	var code := -1
	var tools := Library.tools_root()
	var py := python_command()
	if OS.get_name() == "Windows":
		var quoted: PackedStringArray = []
		for a in args:
			quoted.append('"%s"' % str(a))
		var cmd := 'cd /d "%s" && "%s" %s' % [tools, py, " ".join(quoted)]
		code = OS.execute("cmd.exe", ["/c", cmd], output, true, false)
	else:
		var quoted: PackedStringArray = []
		for a in args:
			quoted.append("'%s'" % str(a))
		var cmd := "cd '%s' && %s %s" % [tools, py, " ".join(quoted)]
		code = OS.execute("/bin/sh", ["-c", cmd], output, true, false)
	call_deferred("_done", code, "\n".join(PackedStringArray(output)))


func _done(code: int, text: String) -> void:
	if _thread and _thread.is_started():
		_thread.wait_to_finish()
	_thread = null
	busy = false
	Library.rescan()
	finished.emit(code == 0, text)
