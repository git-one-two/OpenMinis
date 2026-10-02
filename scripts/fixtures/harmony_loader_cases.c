
static Tracee fresh(LoadInfo *load) {
    Tracee t={0}; t.pid=77; t.load_info=load;
    harmony_loader_prepare(&t,"loader");
    harmony_loader_arm(&t,0x1000);
    t._regs[CURRENT].values[INSTR_POINTER]=0x20000003c4;
    t._regs[CURRENT].values[SYSARG_NUM]=PR_exit;
    t._regs[CURRENT].values[SYSARG_1]=182;
    t._regs[CURRENT].values[STACK_POINTER]=0x900;
    return t;
}
int main(void) {
    LoadInfo load={.user_path="/bin/true",.raw_path="/bin/true"};
    Tracee t;
    reset(); t=fresh(&load);
    harmony_loader_enter(&t);
    assert(t.harmony_loader.retries==1 && t.harmony_loader.force_sysnum);
    assert(t.harmony_loader.retry_exec_in_flight && t.harmony_loader.restarting);
    assert(get_sysnum(&t,CURRENT)==PR_execve && strcmp(last_path,"/bin/true")==0);
    assert(peek_reg(&t,CURRENT,SYSARG_2)==0x1008);
    assert(peek_reg(&t,CURRENT,SYSARG_3)==0x1020);
    assert(stack[1]==0x1234 && stack[2]==0x5678 && stack[4]==0x9999);
    harmony_loader_fail_retry(&t);
    assert(killed==1 && !t.harmony_loader.force_sysnum);
    puts("PASS: retry preserves the kernel argv/envp and failed exec stops only child");

    reset(); load=(LoadInfo){.user_path="/bin/sh",.raw_path="/tmp/test-script"};
    t=fresh(&load);
    for(unsigned n=1;n<=3;n++) {
        harmony_loader_enter(&t); assert(t.harmony_loader.retries==n);
        load.raw_path="/bin/sh";
        harmony_loader_prepare(&t,"loader");
        assert(strcmp(load.raw_path,"/tmp/test-script")==0);
        harmony_loader_arm(&t,0x1000);
        harmony_loader_fail_retry(&t); assert(killed==0);
        assert(t.harmony_loader.retries==n);
        set_sysnum(&t,PR_exit); poke_reg(&t,SYSARG_1,182);
        t.harmony_loader.force_sysnum=false;
    }
    harmony_loader_enter(&t);
    assert(t.harmony_loader.retries==3 && get_sysnum(&t,CURRENT)==PR_exit);
    assert(!t.harmony_loader.force_sysnum);
    harmony_loader_prepare(&t,"loader");
    assert(t.harmony_loader.retries==0);
    puts("PASS: bounded retries, reset on new exec, shebang raw path retained");

    reset(); load=(LoadInfo){.user_path="/bin/true",.raw_path="/bin/true"}; t=fresh(&load);
    set_sysnum(&t,PR_prctl); poke_reg(&t,SYSARG_1,PR_SET_NAME);
    harmony_loader_enter(&t); assert(!t.harmony_loader.active);
    set_sysnum(&t,PR_exit); poke_reg(&t,SYSARG_1,182);
    harmony_loader_enter(&t); assert(t.harmony_loader.retries==0);
    t=fresh(&load); poke_reg(&t,INSTR_POINTER,0x400123);
    harmony_loader_enter(&t); assert(!t.harmony_loader.active && t.harmony_loader.retries==0);
    t=fresh(&load); poke_reg(&t,SYSARG_1,7);
    harmony_loader_enter(&t); assert(t.harmony_loader.retries==0 && get_sysnum(&t,CURRENT)==PR_exit);
    puts("PASS: commit boundary, guest PC and ordinary failures never retry");

    reset(); t=fresh(&load); set_sysnum(&t,PR_openat); poke_reg(&t,SYSARG_3,O_RDONLY);
    harmony_loader_enter(&t); assert(peek_reg(&t,CURRENT,SYSARG_3)&O_CLOEXEC);
    t=fresh(&load); poke_reg(&t,INSTR_POINTER,0x400123); set_sysnum(&t,PR_openat);
    poke_reg(&t,SYSARG_3,O_RDONLY); harmony_loader_enter(&t);
    assert(!(peek_reg(&t,CURRENT,SYSARG_3)&O_CLOEXEC));
    puts("PASS: CLOEXEC applies only to the active loader's ELF open");

    reset(); t=fresh(&load); read_failure=1; harmony_loader_enter(&t);
    assert(t.harmony_loader.retries==0);
    reset(); t=fresh(&load); stack[0]=4097; harmony_loader_enter(&t);
    assert(t.harmony_loader.retries==0);
    reset(); t=fresh(&load); stack[3]=1; harmony_loader_enter(&t);
    assert(t.harmony_loader.retries==0);
    reset(); t=fresh(&load); t.harmony_loader.initial_sp=UINT64_MAX-8;
    harmony_loader_enter(&t); assert(t.harmony_loader.retries==0);
    reset(); t=fresh(&load); path_failure=1;
    struct user_regs_struct saved=t._regs[CURRENT]; bool changed=t._regs_were_changed;
    harmony_loader_enter(&t);
    assert(memcmp(&saved,&t._regs[CURRENT],sizeof saved)==0);
    assert(changed==t._regs_were_changed && t.harmony_loader.retries==0);
    puts("PASS: bad stack and failed path allocation preserve original fatal exit");

    reset(); loader_header.type=ET_DYN; t=fresh(&load); assert(!t.harmony_loader.active);
    reset(); loader_header.class64=false; t=fresh(&load); assert(!t.harmony_loader.active);
    reset(); loader_header.machine=62; t=fresh(&load); assert(!t.harmony_loader.active);
    reset(); loader_program_count=2; loader_programs[1]=loader_programs[0];
    t=fresh(&load); assert(!t.harmony_loader.active);
    reset(); loader_programs[0].vaddr=UINT64_MAX-10; t=fresh(&load); assert(!t.harmony_loader.active);
    reset(); elf_failure=1; t=fresh(&load); assert(!t.harmony_loader.active);
    puts("PASS: unsupported, missing or ambiguous loader identity fails closed");

    reset(); t=fresh(&load); t.is_aarch32=true; harmony_loader_enter(&t); assert(t.harmony_loader.retries==0);
    reset(); t=fresh(&load); t.qemu=&t; harmony_loader_enter(&t); assert(t.harmony_loader.retries==0);
    reset(); t=fresh(&load); t.as_ptracee.ptracer=&t; harmony_loader_enter(&t); assert(t.harmony_loader.retries==0);
    reset(); t=fresh(&load); setenv("PROOT_EXEC_LOADER_RETRY","0",1);
    harmony_loader_enter(&t); assert(t.harmony_loader.retries==0);
    reset(); t=fresh(&load); setenv("PROOT_VERIFY_REGSET","0",1);
    harmony_loader_enter(&t); assert(t.harmony_loader.retries==0);
    puts("PASS: unsupported tracees and disabled verification never recover");

    reset(); Mapping overlap={0x2000000000,4096};
    load.mappings=&overlap; mapping_count=1;
    t=fresh(&load); assert(!t.harmony_loader.active);
    load.mappings=NULL; LoadInfo interpreter={.user_path="/ld.so",.raw_path="/ld.so",.mappings=&overlap};
    load.interp=&interpreter; t=fresh(&load); assert(!t.harmony_loader.active);
    load.interp=NULL;
    puts("PASS: guest or interpreter overlapping loader code cannot recover");
    reset(); puts("PASS: all injected loader-recovery scenarios");
    return 0;
}
