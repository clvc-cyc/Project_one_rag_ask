s="abaa"
left=0
len_max=0
for right in range(1,len(s)):
    if s[left] == s[right]:
        left+=1
    while s[right] in s[left:right-1]:
        left+=1


    len_max=max(len_max,right-left+1)
print( len_max)
