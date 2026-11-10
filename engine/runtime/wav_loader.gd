class_name WavLoader
## Minimal RIFF/WAVE (PCM 8/16-bit) reader producing an AudioStreamWAV.
## Godot 4.3 cannot load WAV files at runtime on its own, so we parse the container here.


static func load(path: String) -> AudioStreamWAV:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		push_warning("WavLoader: cannot open %s" % path)
		return null
	var bytes := f.get_buffer(f.get_length())
	f.close()
	return from_bytes(bytes, path)


static func from_bytes(bytes: PackedByteArray, label: String = "") -> AudioStreamWAV:
	if bytes.size() < 12 or bytes.slice(0, 4).get_string_from_ascii() != "RIFF" \
			or bytes.slice(8, 12).get_string_from_ascii() != "WAVE":
		push_warning("WavLoader: not a RIFF/WAVE file: %s" % label)
		return null
	var pos := 12
	var fmt_tag := 0
	var channels := 1
	var rate := 22050
	var bits := 16
	var data := PackedByteArray()
	var have_fmt := false
	while pos + 8 <= bytes.size():
		var cid := bytes.slice(pos, pos + 4).get_string_from_ascii()
		var size := bytes.decode_u32(pos + 4)
		var body := pos + 8
		if cid == "fmt ":
			fmt_tag = bytes.decode_u16(body)
			channels = bytes.decode_u16(body + 2)
			rate = bytes.decode_u32(body + 4)
			bits = bytes.decode_u16(body + 14)
			have_fmt = true
		elif cid == "data":
			data = bytes.slice(body, mini(body + size, bytes.size()))
		pos = body + size + (size & 1)
	if not have_fmt or data.is_empty():
		push_warning("WavLoader: missing fmt/data chunk: %s" % label)
		return null
	if fmt_tag != 1 and fmt_tag != 0xFFFE:
		push_warning("WavLoader: unsupported WAVE format tag %d: %s" % [fmt_tag, label])
		return null
	var stream := AudioStreamWAV.new()
	stream.mix_rate = rate
	stream.stereo = channels >= 2
	if bits == 8:
		# WAV 8-bit is unsigned; Godot expects signed samples.
		for i in data.size():
			data[i] = (data[i] + 128) & 0xFF
		stream.format = AudioStreamWAV.FORMAT_8_BITS
	elif bits == 16:
		stream.format = AudioStreamWAV.FORMAT_16_BITS
	else:
		push_warning("WavLoader: unsupported bit depth %d: %s" % [bits, label])
		return null
	stream.data = data
	return stream
