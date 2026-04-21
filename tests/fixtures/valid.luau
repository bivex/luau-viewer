local User = {}
User.__index = User

function User.new(id, name)
    local self = setmetatable({}, User)
    self.id = id
    self.name = name
    return self
end

function User:greeting()
    return "Hello, " .. self.name
end

local function makeUser()
    return User.new(1, "Ana")
end

return User
