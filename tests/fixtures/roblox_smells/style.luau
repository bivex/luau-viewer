--!nonstrict
-- style.luau — Code style and architecture smells

local Style = {}

-- magic-numbers: hardcoded values in compound/property assignments
function Style.giveReward(player)
	player.leaderstats.Coins.Value += 15
	player.leaderstats.XP.Value += 50
end

-- global-variable: _G usage in production code
function Style.setGlobal(key, value)
	_G[key] = value
end

-- global-variable: _G with bracket syntax
function Style.readGlobal(key)
	return _G[key]
end

-- deprecated-api: spawn() and wait()
function Style.legacyTimer()
	spawn(function()
		wait(3)
		print("done")
	end)
end

-- deep-nesting: 5 levels of if
function Style.checkPermissions(user)
	if user then
		if user.Team then
			if user.Role then
				if user.Role.Level then
					if user.Role.Level >= 5 then
						return true
					end
				end
			end
		end
	end
	return false
end

-- duplicate-condition: same condition twice
function Style.validate(data)
	if data.age > 18 then
		print("adult")
	end
	if data.age > 18 then
		print("voter")
	end
end

-- identical-actions: same action repeated
function Style.reset()
	local x = 0
	local x = 0
end

-- complex-condition: very long condition
function Style.check(x, y, z, a, b, c, d, e, f)
	if x > 0 and y < 100 and z ~= nil and a == true and b == false and c ~= d and e >= f then
		print("complex")
	end
end

-- nested-loops: 3 levels deep
function Style.tripleLoop(matrix)
	for i = 1, #matrix do
		for j = 1, #matrix[i] do
			for k = 1, #matrix[i][j] do
				print(matrix[i][j][k])
			end
		end
	end
end

-- nested-closures: closures inside closures
function Style.deepCallbacks()
	task.spawn(function()
		task.delay(1, function()
			print("nested callback")
		end)
	end)
end

-- empty-then: if with empty then branch
function Style.checkEmpty(value)
	if value then
	else
		print("missing")
	end
end

-- empty-loop: while loop with no body
function Style.busyWait()
	while false do
	end
end

return Style
