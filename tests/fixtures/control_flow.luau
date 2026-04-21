local MathBox = {}

function MathBox.score(values)
    local total = 0

    for _, value in ipairs(values) do
        if value > 0 then
            total = total + value
        end
    end

    while total > 100 do
        total = total - 10
    end

    repeat
        total = total - 1
    until total <= 50

    for i = 1, total do
        total = total + 1
    end

    return total
end

function MathBox.normalize(input)
    if input < 0 then
        return 0
    end

    return input
end

return MathBox
