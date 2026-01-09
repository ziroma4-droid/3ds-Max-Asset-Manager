-- update_paths.ms
-- Скрипт для обновления путей ассетов в сцене 3ds Max после перемещения файлов
-- Запускается в silent режиме

global g_sceneFile = undefined
global g_pathMappingsFile = undefined

fn initFromArgs = (
    -- Получаем аргументы командной строки
    local args = getCommandLineArgs()
    
    for i = 1 to args.count do (
        local arg = args[i]
        
        if matchPattern arg pattern:"-scene:*" then (
            g_sceneFile = substituteString arg "-scene:" ""
        )
        else if matchPattern arg pattern:"-mappings:*" then (
            g_pathMappingsFile = substituteString arg "-mappings:" ""
        )
    )
    
    return (g_sceneFile != undefined and g_pathMappingsFile != undefined)
)

fn normalizePath pathStr = (
    -- Нормализуем путь: заменяем / на \, убираем двойные слеши
    if pathStr == undefined or pathStr == "" then return ""
    
    local normalized = substituteString pathStr "/" "\\"
    normalized = substituteString normalized "\\\\" "\\"
    
    return normalized
)

fn pathsMatch path1 path2 = (
    -- Сравниваем пути с учетом нормализации
    local norm1 = normalizePath (path1 as string)
    local norm2 = normalizePath (path2 as string)
    
    -- Сравниваем без учета регистра
    return (stricmp norm1 norm2 == 0)
)

fn findNewPath oldPath pathMappings = (
    -- Ищем новый путь для старого пути
    local oldNorm = normalizePath (oldPath as string)
    local oldName = filenameFromPath oldNorm
    local oldNameLower = (toLower oldName)
    
    -- Сначала пытаемся найти точное совпадение пути
    for mapping in pathMappings do (
        local old = normalizePath (mapping[1] as string)
        
        -- Проверяем точное совпадение пути (с учетом регистра и без)
        if pathsMatch old oldNorm then (
            return mapping[2] as string
        )
        
        -- Проверяем, совпадает ли нормализованный абсолютный путь
        try (
            local oldFull = getFullPathName old
            local oldNormFull = getFullPathName oldNorm
            if pathsMatch oldFull oldNormFull then (
                return mapping[2] as string
            )
        ) catch ()
    )
    
    -- Если точное совпадение не найдено, ищем по имени файла
    if oldName != "" and oldNameLower != "" then (
        for mapping in pathMappings do (
            local mappingOld = normalizePath (mapping[1] as string)
            local mappingOldName = filenameFromPath mappingOld
            local mappingOldNameLower = (toLower mappingOldName)
            
            -- Сравниваем имена файлов без учета регистра
            if mappingOldNameLower == oldNameLower then (
                return mapping[2] as string
            )
        )
    )
    
    return undefined
)

fn updateBitmapPaths pathMappings = (
    local updatedCount = 0
    
    -- Обновляем все BitmapTexture
    local allBitmaps = getClassInstances BitmapTexture
    for bmp in allBitmaps do (
        try (
            if bmp.filename != undefined and bmp.filename != "" then (
                local oldPath = bmp.filename
                local newPath = findNewPath oldPath pathMappings
                
                if newPath != undefined and newPath != "" then (
                    local newPathFull = normalizePath newPath
                    
                    -- Проверяем, существует ли файл по новому пути
                    if doesFileExist newPathFull then (
                        bmp.filename = newPathFull
                        updatedCount += 1
                        format "Updated BitmapTexture: % -> %\n" oldPath newPathFull to:stdout
                    ) else (
                        format "Warning: New path does not exist: %\n" newPathFull to:stderr
                    )
                )
            )
        ) catch (
            format "Error updating BitmapTexture: %\n" (getCurrentException()) to:stderr
        )
    )
    
    return updatedCount
)

fn updateVRayProxyPaths pathMappings = (
    local updatedCount = 0
    
    try (
        local proxies = getClassInstances VRayProxy
        for p in proxies do (
            try (
                if p.filename != undefined and p.filename != "" then (
                    local oldPath = p.filename
                    local newPath = findNewPath oldPath pathMappings
                    
                    if newPath != undefined and newPath != "" then (
                        local newPathFull = normalizePath newPath
                        
                        if doesFileExist newPathFull then (
                            p.filename = newPathFull
                            updatedCount += 1
                            format "Updated VRayProxy: % -> %\n" oldPath newPathFull
                        ) else (
                            format "Warning: New path does not exist: %\n" newPathFull
                        )
                    )
                )
            ) catch (
                format "Error updating VRayProxy: %\n" (getCurrentException())
            )
        )
    ) catch ()
    
    return updatedCount
)

fn updateCoronaProxyPaths pathMappings = (
    local updatedCount = 0
    
    try (
        local proxies = getClassInstances CoronaProxy
        for p in proxies do (
            try (
                if p.filename != undefined and p.filename != "" then (
                    local oldPath = p.filename
                    local newPath = findNewPath oldPath pathMappings
                    
                    if newPath != undefined and newPath != "" then (
                        local newPathFull = normalizePath newPath
                        
                        if doesFileExist newPathFull then (
                            p.filename = newPathFull
                            updatedCount += 1
                            format "Updated CoronaProxy: % -> %\n" oldPath newPathFull
                        ) else (
                            format "Warning: New path does not exist: %\n" newPathFull
                        )
                    )
                )
            ) catch (
                format "Error updating CoronaProxy: %\n" (getCurrentException())
            )
        )
    ) catch ()
    
    return updatedCount
)

fn updateXRefPaths pathMappings = (
    local updatedCount = 0
    
    for i = 1 to xrefs.getXRefFileCount() do (
        try (
            local xrefFile = xrefs.getXRefFile i
            if xrefFile != undefined then (
                local oldPath = xrefFile.filename
                if oldPath != undefined and oldPath != "" then (
                    local newPath = findNewPath oldPath pathMappings
                    
                    if newPath != undefined and newPath != "" then (
                        local newPathFull = normalizePath newPath
                        
                        if doesFileExist newPathFull then (
                            xrefs.setXRefFileFilename i newPathFull
                            updatedCount += 1
                            format "Updated XRef: % -> %\n" oldPath newPathFull
                        ) else (
                            format "Warning: New path does not exist: %\n" newPathFull
                        )
                    )
                )
            )
        ) catch (
            format "Error updating XRef: %\n" (getCurrentException())
        )
    )
    
    return updatedCount
)

fn updateAlembicPaths pathMappings = (
    local updatedCount = 0
    
    try (
        local alembics = getClassInstances Alembic_Mesh
        for a in alembics do (
            try (
                if a.filename != undefined and a.filename != "" then (
                    local oldPath = a.filename
                    local newPath = findNewPath oldPath pathMappings
                    
                    if newPath != undefined and newPath != "" then (
                        local newPathFull = normalizePath newPath
                        
                        if doesFileExist newPathFull then (
                            a.filename = newPathFull
                            updatedCount += 1
                            format "Updated Alembic: % -> %\n" oldPath newPathFull
                        ) else (
                            format "Warning: New path does not exist: %\n" newPathFull
                        )
                    )
                )
            ) catch (
                format "Error updating Alembic: %\n" (getCurrentException())
            )
        )
    ) catch ()
    
    return updatedCount
)

fn updateIESPaths pathMappings = (
    local updatedCount = 0
    
    -- V-Ray IES
    try (
        local vrayIES = getClassInstances VRayIES
        for ies in vrayIES do (
            try (
                if ies.iesFile != undefined and ies.iesFile != "" then (
                    local oldPath = ies.iesFile
                    local newPath = findNewPath oldPath pathMappings
                    
                    if newPath != undefined and newPath != "" then (
                        local newPathFull = normalizePath newPath
                        
                        if doesFileExist newPathFull then (
                            ies.iesFile = newPathFull
                            updatedCount += 1
                            format "Updated VRayIES: % -> %\n" oldPath newPathFull
                        ) else (
                            format "Warning: New path does not exist: %\n" newPathFull
                        )
                    )
                )
            ) catch (
                format "Error updating VRayIES: %\n" (getCurrentException())
            )
        )
    ) catch ()
    
    -- Photometric lights
    try (
        local photoLights = getClassInstances freeLight_photometric
        for light in photoLights do (
            try (
                if light.webFile != undefined and light.webFile != "" then (
                    local oldPath = light.webFile
                    local newPath = findNewPath oldPath pathMappings
                    
                    if newPath != undefined and newPath != "" then (
                        local newPathFull = normalizePath newPath
                        
                        if doesFileExist newPathFull then (
                            light.webFile = newPathFull
                            updatedCount += 1
                            format "Updated PhotometricLight: % -> %\n" oldPath newPathFull
                        ) else (
                            format "Warning: New path does not exist: %\n" newPathFull
                        )
                    )
                )
            ) catch (
                format "Error updating PhotometricLight: %\n" (getCurrentException())
            )
        )
    ) catch ()
    
    return updatedCount
)

fn readPathMappings = (
    -- Читаем файл с маппингом путей (формат: старый_путь|новый_путь на каждой строке)
    local mappings = #()
    
    try (
        local f = openFile g_pathMappingsFile mode:"r"
        if f != undefined then (
            while not eof f do (
                local line = readLine f
                if line != undefined and line != "" then (
                    -- Разделяем строку по символу |
                    local parts = filterString line "|"
                    if parts.count == 2 then (
                        append mappings #(parts[1], parts[2])
                    )
                )
            )
            close f
        )
    ) catch (
        format "Error reading path mappings file: %\n" (getCurrentException())
    )
    
    return mappings
)

fn main = (
    -- Отключаем лишние сообщения для более чистого вывода
    quietMode = true
    
    if not initFromArgs() then (
        format "Error: Missing arguments\n"
        format "Usage: 3dsmax.exe -silent -mxs \"update_paths.ms\" -scene:<path> -mappings:<path>\n"
        quitMax #noPrompt
        return false
    )
    
    -- Проверяем, не открыта ли сцена в другом экземпляре 3ds Max
    if maxFilePath != "" then (
        format "Warning: A scene is already open: %\n" maxFilePath
        format "Please close the scene first or run 3ds Max in silent mode\n"
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
    
    -- Читаем маппинг путей
    local pathMappings = readPathMappings()
    format "Loaded % path mappings\n" pathMappings.count
    
    if pathMappings.count == 0 then (
        format "Warning: No path mappings found\n"
        quitMax #noPrompt
        return true
    )
    
    -- Обновляем пути
    local totalUpdated = 0
    
    format "Updating paths...\n"
    totalUpdated += updateBitmapPaths pathMappings
    totalUpdated += updateVRayProxyPaths pathMappings
    totalUpdated += updateCoronaProxyPaths pathMappings
    totalUpdated += updateXRefPaths pathMappings
    totalUpdated += updateAlembicPaths pathMappings
    totalUpdated += updateIESPaths pathMappings
    
    format "Total paths updated: %\n" totalUpdated
    
    -- Сохраняем сцену
    format "Saving scene...\n"
    
    -- Проверяем, существует ли файл и его атрибуты
    local sceneExists = doesFileExist g_sceneFile
    if sceneExists then (
        format "Scene file exists: %\n" g_sceneFile
        
        -- Проверяем, не является ли файл только для чтения
        try (
            local sceneDir = getFilenamePath g_sceneFile
            local sceneName = filenameFromPath g_sceneFile
            
            -- В MaxScript нет прямого способа проверить read-only, поэтому пробуем создать временный файл
            local testFilePath = sceneDir + "~test_write_permission.tmp"
            local testFile = createFile testFilePath
            if testFile != undefined then (
                close testFile
                deleteFile testFilePath
                format "Write permission: OK\n"
            ) else (
                format "Warning: Cannot write to scene directory\n"
            )
        ) catch (
            format "Warning: Error checking write permission: %\n" (getCurrentException())
        )
    ) else (
        format "Warning: Scene file does not exist before save: %\n" g_sceneFile
    )
    
    -- Пробуем сохранить сцену
    local saveResult = false
    try (
        -- Сначала пробуем обычное сохранение
        format "Attempting to save scene: %\n" g_sceneFile
        saveResult = saveMaxFile g_sceneFile quiet:true useNewFile:false
        
        if saveResult then (
            format "Scene saved successfully (method 1)\n"
        ) else (
            -- Если не получилось, пробуем с useNewFile
            format "Trying alternative save method (useNewFile:true)...\n"
            saveResult = saveMaxFile g_sceneFile quiet:true useNewFile:true
            
            if saveResult then (
                format "Scene saved successfully (method 2)\n"
            ) else (
                -- Пробуем сохранить через saveMaxFile с полным путем
                format "Trying saveMaxFile with full path...\n"
                local fullPath = getFullPathName g_sceneFile
                saveResult = saveMaxFile fullPath quiet:true
                
                if saveResult then (
                    format "Scene saved successfully (method 3)\n"
                ) else (
                    format "All save methods failed\n"
                )
            )
        )
    ) catch (
        format "Error saving scene: %\n" (getCurrentException())
        saveResult = false
    )
    
    if saveResult then (
        format "Scene saved successfully\n"
    ) else (
        format "Error: Failed to save scene. Path: %\n" g_sceneFile
        format "Please check file permissions and make sure the file is not read-only\n"
    )
    
    quitMax #noPrompt
    return saveResult
)

-- Запуск
main()
