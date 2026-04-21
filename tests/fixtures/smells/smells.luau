-- Triggers: deprecated-api, empty-function, infinite-loop, wait-in-loop
local Smells = {}

function Smells.empty()
end

function Smells.process(items)
	spawn(function()
		print("started")
	end)
	wait(0.1)
	while true do
		local x = 1
	end
	for i = 1, 10 do
		task.wait(1)
	end
	return items
end

function Smells.nested(x)
	if x > 0 then
		if x > 10 then
			if x > 20 then
				if x > 30 then
					if x > 40 then
						return x
					end
				end
			end
		end
	end
	return 0
end

function Smells.unreachable()
	return 1
	print("never reached")
end

return Smells
