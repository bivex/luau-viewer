--!nonstrict
-- performance.luau — Performance smells in a Roblox game loop

local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Performance = {}

-- instance-in-loop: Instance.new inside a for loop
function Performance.spawnWave(count)
	for i = 1, count do
		local part = Instance.new("Part")
		part.Size = Vector3.new(4, 4, 4)
		part.Position = Vector3.new(i * 10, 10, 0)
		part.Parent = workspace
	end
end

-- getchildren-in-loop: :GetChildren() called every iteration
function Performance.pollMap()
	while true do
		local children = workspace.Map:GetChildren()
		for _, child in ipairs(children) do
			print(child.Name)
		end
		break
	end
end

-- task-spawn-storm: spawning coroutines in a tight loop
function Performance.batchProcess(items)
	for i = 1, #items do
		task.spawn(function()
			print(items[i])
		end)
	end
end

-- require-in-loop: requiring module every iteration
function Performance.loadModules(moduleList)
	for _, moduleName in ipairs(moduleList) do
		local mod = require(ReplicatedStorage:FindFirstChild(moduleName))
		mod:init()
	end
end

-- remote-spam: :FireServer inside a frame signal
-- connect-leak: :Connect without cleanup
function Performance.syncPosition()
	RunService.Heartbeat:Connect(function()
		ReplicatedStorage.PositionRemote:FireServer(workspace.CurrentCamera.CFrame.Position)
	end)
end

-- empty-loop: loop with no body
function Performance.idleWait()
	for i = 1, 60 do
	end
end

-- wait-in-loop: deprecated wait() inside loop
function Performance.countdown()
	for i = 10, 1, -1 do
		wait(1)
	end
end

return Performance
