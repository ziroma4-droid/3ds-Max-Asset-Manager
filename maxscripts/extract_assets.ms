-- extract_assets.ms
-- Скрипт для извлечения путей ассетов из сцены 3ds Max
-- Запускается в silent режиме

global g_outputFile = undefined
global g_sceneFile = undefined

fn initFromArgs = (
    -- Получаем аргументы командной строки
    local args = getCommandLineArgs()
    
    for i = 1 to args.count do (
        local arg = args[i]
        
        if matchPattern arg pattern:"-scene:*" then (
            g_sceneFile = substituteString arg "-scene:" ""
        )
        else if matchPattern arg pattern:"-output:*" then (
            g_outputFile = substituteString arg "-output:" ""
        )
    )
    
    return (g_sceneFile != undefined and g_outputFile != undefined)
)

fn collectBitmapPaths = (
    local paths = #()
    
    -- Собираем все текстуры из материалов
    for m in sceneMaterials do (
        try (
            local maps = getClassInstances BitmapTexture target:m
            for bmp in maps do (
                if bmp.filename != undefined and bmp.filename != "" do (
                    appendIfUnique paths bmp.filename
                )
            )
        ) catch ()
    )
    
    -- Собираем из всех BitmapTexture в сцене
    local allBitmaps = getClassInstances BitmapTexture
    for bmp in allBitmaps do (
        try (
            if bmp.filename != undefined and bmp.filename != "" do (
                appendIfUnique paths bmp.filename
            )
        ) catch ()
    )
    
    return paths
)

fn collectVRayProxyPaths = (
    local paths = #()
    
    -- V-Ray Proxy
    try (
        local proxies = getClassInstances VRayProxy
        for p in proxies do (
            if p.filename != undefined and p.filename != "" do (
                appendIfUnique paths p.filename
            )
        )
    ) catch ()
    
    return paths
)

fn collectCoronaProxyPaths = (
    local paths = #()
    
    -- Corona Proxy
    try (
        local proxies = getClassInstances CoronaProxy
        for p in proxies do (
            if p.filename != undefined and p.filename != "" do (
                appendIfUnique paths p.filename
            )
        )
    ) catch ()
    
    return paths
)

fn collectXRefPaths = (
    local paths = #()
    
    -- XRef Objects
    for i = 1 to xrefs.getXRefFileCount() do (
        try (
            local xrefFile = xrefs.getXRefFile i
            if xrefFile != undefined do (
                local path = xrefFile.filename
                if path != undefined and path != "" do (
                    appendIfUnique paths path
                )
            )
        ) catch ()
    )
    
    return paths
)

fn collectAlembicPaths = (
    local paths = #()
    
    -- Alembic containers
    try (
        local alembics = getClassInstances Alembic_Mesh
        for a in alembics do (
            if a.filename != undefined and a.filename != "" do (
                appendIfUnique paths a.filename
            )
        )
    ) catch ()
    
    return paths
)

fn collectIESPaths = (
    local paths = #()
    
    -- IES файлы из источников света
    try (
        -- V-Ray IES
        local vrayIES = getClassInstances VRayIES
        for ies in vrayIES do (
            if ies.iesFile != undefined and ies.iesFile != "" do (
                appendIfUnique paths ies.iesFile
            )
        )
    ) catch ()
    
    try (
        -- Photometric lights
        local photoLights = getClassInstances freeLight_photometric
        for light in photoLights do (
            if light.webFile != undefined and light.webFile != "" do (
                appendIfUnique paths light.webFile
            )
        )
    ) catch ()
    
    return paths
)

fn collectAllAssets = (
    local allPaths = #()
    
    -- Собираем все типы ассетов
    join allPaths (collectBitmapPaths())
    join allPaths (collectVRayProxyPaths())
    join allPaths (collectCoronaProxyPaths())
    join allPaths (collectXRefPaths())
    join allPaths (collectAlembicPaths())
    join allPaths (collectIESPaths())
    
    return allPaths
)

fn writeOutputFile paths = (
    local f = createFile g_outputFile
    
    if f != undefined then (
        format "ASSET_LIST_START\n" to:f
        
        for p in paths do (
            format "%\n" p to:f
        )
        
        format "ASSET_LIST_END\n" to:f
        close f
        return true
    )
    
    return false
)

fn main = (
    if not initFromArgs() then (
        format "Error: Missing arguments\n"
        format "Usage: 3dsmax.exe -silent -mxs \"extract_assets.ms\" -scene:<path> -output:<path>\n"
        quitMax #noPrompt
        return false
    )
    
    -- Загружаем сцену
    format "Loading scene: %\n" g_sceneFile
    
    local loadResult = loadMaxFile g_sceneFile quiet:true
    
    if not loadResult then (
        format "Error: Failed to load scene\n"
        quitMax #noPrompt
        return false
    )
    
    format "Scene loaded successfully\n"
    
    -- Собираем ассеты
    local assets = collectAllAssets()
    format "Found % assets\n" assets.count
    
    -- Записываем результат
    if writeOutputFile assets then (
        format "Output written to: %\n" g_outputFile
    ) else (
        format "Error: Failed to write output file\n"
    )
    
    quitMax #noPrompt
    return true
)

-- Запуск
main()